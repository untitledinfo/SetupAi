"""FIREWING Python SDK.

Minimal client for the FIREWING API — no external dependencies beyond
`requests`, deliberately kept small rather than wrapping the OpenAI SDK
(which would imply a compatibility guarantee this beta doesn't make
yet).

Usage:
    from firewing_sdk import FirewingClient

    client = FirewingClient(base_url="http://localhost:8000", api_key="...")
    reply = client.chat([{"role": "user", "content": "Hello"}])
    print(reply)

    for chunk in client.chat_stream([{"role": "user", "content": "Hello"}]):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import json
from typing import Iterator

import requests


class FirewingError(RuntimeError):
    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


class FirewingClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def health(self) -> dict:
        resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat(
        self,
        messages: list[dict],
        model: str = "firewing-1.0-beta",
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        persona: str | None = None,
    ) -> str:
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
            "persona": persona,
        }
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        if not resp.ok:
            self._raise_for_error(resp)
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_stream(
        self,
        messages: list[dict],
        model: str = "firewing-1.0-beta",
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        persona: str | None = None,
    ) -> Iterator[str]:
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": True,
            "persona": persona,
        }
        with requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
            stream=True,
        ) as resp:
            if not resp.ok:
                self._raise_for_error(resp)
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                yield payload

    def _raise_for_error(self, resp: requests.Response) -> None:
        try:
            err = resp.json().get("error", {})
            raise FirewingError(
                err.get("message", resp.text), request_id=err.get("request_id")
            )
        except (json.JSONDecodeError, ValueError):
            raise FirewingError(f"HTTP {resp.status_code}: {resp.text}")
