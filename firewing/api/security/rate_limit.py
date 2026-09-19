"""In-memory per-key rate limiting (token bucket).

In-memory is a known beta limitation: it does not share state across
multiple server processes/replicas. For a multi-worker or
multi-instance deployment, swap this for a Redis-backed limiter before
going to production at scale — see docs/troubleshooting.md.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, status


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    def __init__(self, requests_per_minute: int):
        self.capacity = max(requests_per_minute, 1)
        self.refill_rate_per_sec = self.capacity / 60.0
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=self.capacity, last_refill=time.monotonic())
        )
        self._lock = Lock()

    def check(self, key: str) -> None:
        with self._lock:
            bucket = self._buckets[key]
            now = time.monotonic()
            elapsed = now - bucket.last_refill
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate_per_sec)
            bucket.last_refill = now

            if bucket.tokens < 1:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )
            bucket.tokens -= 1
