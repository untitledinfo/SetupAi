from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from firewing.config.settings import load_settings
from firewing.api.routes import health, chat, conversations
from firewing.api.admin import routes as admin_routes
from firewing.api.security.rate_limit import RateLimiter
from firewing.api.security.key_store import KeyStore
from firewing.inference.conversation_store import ConversationStore
from firewing.model.loader import load_model, ModelLoadError
from firewing.inference.engine import InferenceEngine
from firewing.utils.logging import configure_logging, get_logger
from firewing.utils.stats import StatsTracker

logger = get_logger("api.server")


def create_app(config_path: str | None = None, lazy_load_model: bool = False) -> FastAPI:
    settings = load_settings(config_path)
    configure_logging(
        level=settings.logging.level,
        log_dir=settings.logging.log_dir,
        json_logs=settings.logging.json_logs,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not lazy_load_model:
            try:
                loaded = load_model(settings.model)
                app.state.engine = InferenceEngine(
                    loaded, settings.model.max_context_tokens, settings.model.context_strategy
                )
                logger.info("Model loaded successfully")
            except ModelLoadError as exc:
                # Don't crash the process — /health still reports OK for
                # infra checks, but chat requests will 503 until fixed.
                # This lets an operator start the service, see the error
                # in logs, and fix config without a crash loop.
                logger.error("Model failed to load: %s", exc)
        yield

    app = FastAPI(title="FIREWING API", version="1.0.0-beta", lifespan=lifespan)
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.api.rate_limit_requests_per_minute)
    app.state.engine = None
    app.state.key_store = KeyStore(f"{settings.data_dir}/api_keys.json")
    app.state.conversation_store = ConversationStore(f"{settings.data_dir}/conversations.db")
    app.state.stats_tracker = StatsTracker()

    if settings.api.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api.cors_allowed_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        logger.error("Unhandled error request_id=%s: %s", request_id, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "An internal error occurred",
                    "request_id": request_id,
                }
            },
        )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(admin_routes.router)

    return app


# `uvicorn firewing.api.server:app` entrypoint
app = create_app()
