from fastapi.testclient import TestClient

import app as be_my_lens


def client() -> TestClient:
    return TestClient(be_my_lens.app)


def test_translate_text_returns_answer(monkeypatch):
    monkeypatch.setattr(be_my_lens, "OPENAI_API_KEY", "test-key")
    captured = {}

    async def fake_ask_text_model(developer_prompt, user_text):
        captured["developer_prompt"] = developer_prompt
        captured["user_text"] = user_text
        return "مرحبا"

    monkeypatch.setattr(be_my_lens, "ask_text_model", fake_ask_text_model)

    response = client().post("/translate_text", json={"text": "hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "مرحبا"}
    assert captured["user_text"] == "hello"
    assert captured["developer_prompt"] == be_my_lens.TRANSLATE_TEXT_PROMPT


def test_translate_text_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(be_my_lens, "OPENAI_API_KEY", "test-key")

    response = client().post("/translate_text", json={"text": ""})

    assert response.status_code == 400


def test_translate_text_rejects_whitespace_text(monkeypatch):
    monkeypatch.setattr(be_my_lens, "OPENAI_API_KEY", "test-key")

    response = client().post("/translate_text", json={"text": "   "})

    assert response.status_code == 400
