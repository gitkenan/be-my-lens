"""Test doubles and request helpers for the backend suite (fixtures live in conftest.py)."""

import json
from collections import deque

import httpx
from fastapi.testclient import TestClient

TEST_API_KEY = "sk-test-not-a-real-key"

# A PNG signature plus payload. The backend never decodes images, it only forwards
# them, so what matters is that these exact bytes reach the model request.
SAMPLE_IMAGE = b"\x89PNG\r\n\x1a\n" + b"be-my-lens-test-image"


class FakeOpenAI:
    """Stands in for api.openai.com at the httpx transport layer.

    Replies are queued explicitly with ``will_answer`` / ``will_respond`` /
    ``will_raise``. A model call with nothing queued is recorded as unexpected and
    fails the test at teardown, so a test can never silently rely on a default reply.
    ``will_answer`` replies in whichever wire format the app called (Responses API or
    Chat Completions), as the real service would.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.unexpected_requests: list[httpx.Request] = []
        self._replies: deque = deque()

    # Queueing replies -------------------------------------------------------------

    def will_answer(self, text: str) -> None:
        self._replies.append(("answer", text))

    def will_respond(self, status_code: int, json_body=None, text: str | None = None) -> None:
        self._replies.append(("raw", (status_code, json_body, text)))

    def will_raise(self, error: Exception) -> None:
        self._replies.append(("raise", error))

    # Inspecting what the app sent ------------------------------------------------

    @property
    def calls(self) -> list[dict]:
        """JSON bodies the app sent upstream, each tagged with the URL it went to."""
        return [{"url": str(request.url), **json.loads(request.content)} for request in self.requests]

    @property
    def last_call(self) -> dict:
        assert self.requests, "the app made no model call"
        return self.calls[-1]

    # Transport -------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not self._replies:
            self.unexpected_requests.append(request)
            return httpx.Response(599, text="FakeOpenAI: no reply queued for this call")

        self.requests.append(request)
        kind, value = self._replies.popleft()
        if kind == "raise":
            raise value
        if kind == "raw":
            status_code, json_body, text = value
            if json_body is not None:
                return httpx.Response(status_code, json=json_body)
            return httpx.Response(status_code, text=text or "")
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json=chat_completion_payload(value))
        return httpx.Response(200, json=responses_api_payload(value))


def responses_api_payload(*texts: str) -> dict:
    """Minimal Responses API body; like real replies it leads with a reasoning item."""
    return {
        "id": "resp_test",
        "object": "response",
        "output": [
            {"type": "reasoning", "id": "rs_test", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text} for text in texts],
            },
        ],
    }


def chat_completion_payload(content) -> dict:
    return {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def upload(image: bytes = SAMPLE_IMAGE, content_type: str = "image/jpeg") -> dict:
    """Multipart ``files=`` argument shaped like the Android app's upload."""
    return {"image": ("image.jpg", image, content_type)}


def start_session(client: TestClient, fake_openai: FakeOpenAI, description: str = "A red door.") -> str:
    """Describe an image the way the app does first, and return the new session id."""
    fake_openai.will_answer(description)
    response = client.post("/describe", files=upload())
    assert response.status_code == 200, response.text
    return response.json()["sessionId"]
