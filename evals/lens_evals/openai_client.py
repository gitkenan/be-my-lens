"""A deliberately small async client for the OpenAI Responses API.

Shared by the model under test and the judge. Retries transient failures
(429, 5xx, network errors) with exponential backoff; other errors fail fast.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_S = 90.0  # same as the backend
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class ResponsesClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = 2,
        backoff_s: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._url = base_url.rstrip("/") + "/responses"
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            timeout=timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    async def __aenter__(self) -> "ResponsesClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = await self._http.post(self._url, json=payload)
            except httpx.TransportError as exc:
                error = OpenAIError(f"Network error calling OpenAI: {exc}")
            else:
                if response.status_code < 400:
                    return response.json()
                error = OpenAIError(
                    f"OpenAI returned HTTP {response.status_code}: {_error_message(response)}",
                    status_code=response.status_code,
                )
                if response.status_code not in _RETRYABLE_STATUS:
                    raise error

            if attempt >= self._max_retries:
                raise error
            await self._sleep(self._backoff_s * (2**attempt))
            attempt += 1


def _error_message(response: httpx.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message")
    except (ValueError, AttributeError):
        message = None
    return message or response.text.strip()[:500] or "<empty body>"


def extract_output_text(data: dict[str, Any]) -> str:
    """Concatenate ``output_text`` chunks from message items (same logic as the backend)."""
    chunks: list[str] = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)
