"""Every model-backed endpoint fails the same, predictable way when OpenAI cannot help.

The app shows these failures to a blind user, so they must be clean HTTP errors, and a
failed request must never leave a half-created session behind.
"""

import httpx
import pytest

import app as be_my_lens
from support import responses_api_payload, start_session, upload


def _describe(client, fake_openai):
    return lambda: client.post("/describe", files=upload())


def _read(client, fake_openai):
    return lambda: client.post("/read", files=upload())


def _chat(client, fake_openai):
    return lambda: client.post("/chat", files=upload(), data={"question": "What is this?"})


def _followup(client, fake_openai):
    session_id = start_session(client, fake_openai)
    return lambda: client.post("/followup", json={"sessionId": session_id, "question": "And then?"})


def _translate_text(client, fake_openai):
    return lambda: client.post("/translate_text", json={"text": "hello"})


ENDPOINTS = {
    "describe": _describe,
    "read": _read,
    "chat": _chat,
    "followup": _followup,
    "translate_text": _translate_text,
}


@pytest.fixture(params=list(ENDPOINTS))
def send(request, client, fake_openai):
    """Sets up any prerequisite state, then returns a callable that hits the endpoint once."""
    return ENDPOINTS[request.param](client, fake_openai)


def test_missing_api_key_is_a_server_error_and_nothing_is_sent(send, fake_openai, monkeypatch):
    monkeypatch.setattr(be_my_lens, "OPENAI_API_KEY", None)
    calls_before = len(fake_openai.requests)

    response = send()

    assert response.status_code == 500
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert len(fake_openai.requests) == calls_before


@pytest.mark.parametrize("status_code", [400, 401, 429, 500, 503])
def test_upstream_http_error_becomes_bad_gateway_with_upstream_detail(send, fake_openai, status_code):
    sessions_before = dict(be_my_lens.SESSIONS)
    fake_openai.will_respond(status_code, json_body={"error": {"message": "upstream said no"}})

    response = send()

    assert response.status_code == 502
    assert "upstream said no" in response.json()["detail"]
    assert be_my_lens.SESSIONS == sessions_before


@pytest.mark.parametrize(
    "empty_reply",
    [
        pytest.param({"output": []}, id="responses-no-output"),
        pytest.param(responses_api_payload(""), id="responses-empty-text"),
        pytest.param({"choices": []}, id="chat-no-choices"),
        pytest.param({"choices": [{"message": {"role": "assistant", "content": None}}]}, id="chat-null-content"),
    ],
)
def test_model_reply_without_text_becomes_bad_gateway(send, fake_openai, empty_reply):
    sessions_before = dict(be_my_lens.SESSIONS)
    fake_openai.will_respond(200, json_body=empty_reply)

    response = send()

    assert response.status_code == 502
    assert be_my_lens.SESSIONS == sessions_before


@pytest.mark.parametrize(
    "error, detail",
    [
        pytest.param(httpx.ConnectError("connection refused"), be_my_lens.MODEL_UNREACHABLE_DETAIL, id="connect-error"),
        pytest.param(
            httpx.RemoteProtocolError("peer closed connection"), be_my_lens.MODEL_UNREACHABLE_DETAIL, id="dropped"
        ),
        pytest.param(httpx.ConnectTimeout("connect timed out"), be_my_lens.MODEL_TIMEOUT_DETAIL, id="connect-timeout"),
        pytest.param(httpx.ReadTimeout("read timed out"), be_my_lens.MODEL_TIMEOUT_DETAIL, id="read-timeout"),
    ],
)
def test_unreachable_model_becomes_bad_gateway_with_readable_detail(send, fake_openai, error, detail):
    sessions_before = dict(be_my_lens.SESSIONS)
    fake_openai.will_raise(error)

    response = send()

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    assert be_my_lens.SESSIONS == sessions_before


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("<html>502 Bad Gateway</html>", id="html-error-page"),
        pytest.param("", id="empty-body"),
        pytest.param('["not", "an", "object"]', id="json-array"),
    ],
)
def test_unusable_model_reply_becomes_bad_gateway_with_readable_detail(send, fake_openai, body):
    sessions_before = dict(be_my_lens.SESSIONS)
    fake_openai.will_respond(200, text=body)

    response = send()

    assert response.status_code == 502
    assert response.json() == {"detail": be_my_lens.MODEL_INVALID_REPLY_DETAIL}
    assert be_my_lens.SESSIONS == sessions_before
