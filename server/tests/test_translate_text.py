"""/translate_text: text selected in Jieshuo is translated without any image."""

import pytest

import app as be_my_lens


def test_translate_text_returns_answer(client, fake_openai):
    fake_openai.will_answer(" مرحبا \n")

    response = client.post("/translate_text", json={"text": "hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "مرحبا"}


def test_translate_text_sends_trimmed_text_with_translation_prompt_and_no_image(client, fake_openai):
    fake_openai.will_answer("المخرج 12A")

    client.post("/translate_text", json={"text": "  Exit 12A\nis ahead  "})

    call = fake_openai.last_call
    assert call["url"] == be_my_lens.OPENAI_RESPONSES_API_URL
    assert call["model"] == be_my_lens.OPENAI_MODEL
    assert call["input"] == [
        {"role": "developer", "content": [{"type": "input_text", "text": be_my_lens.TRANSLATE_TEXT_PROMPT}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Exit 12A\nis ahead"}]},
    ]


def test_translate_text_does_not_open_a_session(client, fake_openai):
    fake_openai.will_answer("مرحبا")

    response = client.post("/translate_text", json={"text": "hello"})

    assert "sessionId" not in response.json()
    assert be_my_lens.SESSIONS == {}


@pytest.mark.parametrize("text", ["", "   ", "\n\t"], ids=["empty", "spaces", "whitespace"])
def test_translate_text_rejects_blank_text(client, fake_openai, text):
    response = client.post("/translate_text", json={"text": text})

    assert response.status_code == 400
    assert fake_openai.requests == []


def test_translate_text_rejects_body_without_text(client, fake_openai):
    response = client.post("/translate_text", json={"message": "hello"})

    assert response.status_code == 422
    assert fake_openai.requests == []
