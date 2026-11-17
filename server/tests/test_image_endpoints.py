"""/describe, /read and /chat: an uploaded image goes to the model and an answer comes back."""

import base64
import re

import pytest

import app as be_my_lens
from support import SAMPLE_IMAGE, TEST_API_KEY, chat_completion_payload, responses_api_payload, upload

SAMPLE_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(SAMPLE_IMAGE).decode()

# (endpoint, response field, developer prompt, fixed user question)
ONE_SHOT_IMAGE_ENDPOINTS = [
    pytest.param("/describe", "description", "DESCRIBE_IMAGE_PROMPT", "DESCRIBE_IMAGE_QUESTION", id="describe"),
    pytest.param("/read", "contents", "READ_CONTENTS_PROMPT", "READ_CONTENTS_QUESTION", id="read"),
]


@pytest.mark.parametrize("path, field, prompt_name, question_name", ONE_SHOT_IMAGE_ENDPOINTS)
def test_returns_model_answer_with_new_session(client, fake_openai, path, field, prompt_name, question_name):
    fake_openai.will_answer("  باب أحمر عليه لافتة خروج.\n")

    response = client.post(path, files=upload())

    assert response.status_code == 200
    body = response.json()
    assert body[field] == "باب أحمر عليه لافتة خروج."
    assert re.fullmatch(r"[0-9a-f]{32}", body["sessionId"])


@pytest.mark.parametrize("path, field, prompt_name, question_name", ONE_SHOT_IMAGE_ENDPOINTS)
def test_sends_image_and_task_prompt_to_responses_api(client, fake_openai, path, field, prompt_name, question_name):
    fake_openai.will_answer("answer")

    client.post(path, files=upload())

    request = fake_openai.requests[-1]
    assert str(request.url) == be_my_lens.OPENAI_RESPONSES_API_URL
    assert request.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
    call = fake_openai.last_call
    assert call["model"] == be_my_lens.OPENAI_MODEL
    developer, user = call["input"]
    assert developer["role"] == "developer"
    assert developer["content"] == [{"type": "input_text", "text": getattr(be_my_lens, prompt_name)}]
    assert user["role"] == "user"
    assert user["content"] == [
        {"type": "input_text", "text": getattr(be_my_lens, question_name)},
        {"type": "input_image", "image_url": SAMPLE_DATA_URL, "detail": "high"},
    ]


def test_uploaded_content_type_is_kept_in_image_data_url(client, fake_openai):
    fake_openai.will_answer("answer")

    client.post("/describe", files=upload(content_type="image/png"))

    image_part = fake_openai.last_call["input"][1]["content"][1]
    assert image_part["image_url"].startswith("data:image/png;base64,")


def test_each_image_gets_its_own_session(client, fake_openai):
    fake_openai.will_answer("first")
    fake_openai.will_answer("second")

    first = client.post("/describe", files=upload(b"image-one")).json()
    second = client.post("/read", files=upload(b"image-two")).json()

    assert first["sessionId"] != second["sessionId"]


def test_multi_part_model_output_is_joined_and_reasoning_items_ignored(client, fake_openai):
    fake_openai.will_respond(200, responses_api_payload("Exit 12A", "King Fahd Road"))

    response = client.post("/read", files=upload())

    assert response.json()["contents"] == "Exit 12A\nKing Fahd Road"


@pytest.mark.parametrize("path", ["/describe", "/read", "/chat"])
def test_empty_image_is_rejected_before_calling_model(client, fake_openai, path):
    response = client.post(path, files=upload(b""), data={"question": "What is this?"})

    assert response.status_code == 400
    assert fake_openai.requests == []
    assert be_my_lens.SESSIONS == {}


@pytest.mark.parametrize("path", ["/describe", "/read", "/chat"])
def test_request_without_image_is_rejected(client, fake_openai, path):
    response = client.post(path, data={"question": "What is this?"})

    assert response.status_code == 422
    assert fake_openai.requests == []


class TestChat:
    """/chat: the first question about a new image (the app's "ask a question" path)."""

    def test_answers_question_about_uploaded_image(self, client, fake_openai):
        fake_openai.will_answer(" الزر الأحمر في الأعلى. ")

        response = client.post("/chat", files=upload(), data={"question": "  أين الزر الأحمر؟ "})

        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "الزر الأحمر في الأعلى."
        assert re.fullmatch(r"[0-9a-f]{32}", body["sessionId"])

    def test_sends_trimmed_question_with_image_to_chat_completions(self, client, fake_openai):
        fake_openai.will_answer("answer")

        client.post("/chat", files=upload(), data={"question": "  Is the door open?  "})

        call = fake_openai.last_call
        assert call["url"] == be_my_lens.OPENAI_CHAT_COMPLETIONS_API_URL
        assert call["model"] == be_my_lens.OPENAI_MODEL
        assert call["messages"] == [
            {"role": "developer", "content": be_my_lens.ASK_QUESTION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Is the door open?"},
                    {"type": "image_url", "image_url": {"url": SAMPLE_DATA_URL, "detail": "high"}},
                ],
            },
        ]

    @pytest.mark.parametrize("question", ["", "   \n\t"])
    def test_blank_question_is_rejected_before_calling_model(self, client, fake_openai, question):
        response = client.post("/chat", files=upload(), data={"question": question})

        assert response.status_code == 400
        assert fake_openai.requests == []
        assert be_my_lens.SESSIONS == {}

    def test_answer_given_as_content_parts_is_joined(self, client, fake_openai):
        fake_openai.will_respond(
            200,
            chat_completion_payload(
                [
                    {"type": "text", "text": "First line."},
                    {"type": "refusal", "refusal": "ignored"},
                    {"type": "text", "text": "Second line."},
                ]
            ),
        )

        response = client.post("/chat", files=upload(), data={"question": "What is this?"})

        assert response.json()["answer"] == "First line.\nSecond line."
