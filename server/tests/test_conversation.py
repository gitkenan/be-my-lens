"""/followup: multi-turn conversations about the image of an earlier /describe, /read or /chat.

These follow the app's real flow (open a session, then ask follow-ups) and check what
context the model receives on each turn.
"""

import base64

import app as be_my_lens
from support import SAMPLE_IMAGE, start_session, upload

SAMPLE_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(SAMPLE_IMAGE).decode()


def ask(client, fake_openai, session_id: str, question: str, answer: str):
    fake_openai.will_answer(answer)
    return client.post("/followup", json={"sessionId": session_id, "question": question})


def history_sent(fake_openai) -> list[tuple[str, str]]:
    """(role, text) turns between the developer prompt and the new question."""
    messages = fake_openai.last_call["messages"]
    return [(message["role"], message["content"]) for message in messages[1:-1]]


def new_question_sent(fake_openai) -> dict:
    return fake_openai.last_call["messages"][-1]


def test_follow_up_is_answered_with_image_and_description_as_context(client, fake_openai):
    session_id = start_session(client, fake_openai, description="A red door with an EXIT sign.")

    response = ask(client, fake_openai, session_id, "  Is the door open? ", " It is closed. ")

    assert response.status_code == 200
    assert response.json() == {"answer": "It is closed."}
    call = fake_openai.last_call
    assert call["url"] == be_my_lens.OPENAI_CHAT_COMPLETIONS_API_URL
    assert call["messages"][0] == {"role": "developer", "content": be_my_lens.ASK_QUESTION_PROMPT}
    assert history_sent(fake_openai) == [
        ("user", be_my_lens.DESCRIBE_IMAGE_QUESTION),
        ("assistant", "A red door with an EXIT sign."),
    ]
    assert new_question_sent(fake_openai) == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Is the door open?"},
            {"type": "image_url", "image_url": {"url": SAMPLE_DATA_URL, "detail": "high"}},
        ],
    }


def test_each_follow_up_sees_the_previous_exchanges(client, fake_openai):
    session_id = start_session(client, fake_openai, description="A kitchen.")
    ask(client, fake_openai, session_id, "Is the stove on?", "No.")

    ask(client, fake_openai, session_id, "Anything on the counter?", "A kettle.")

    assert history_sent(fake_openai) == [
        ("user", be_my_lens.DESCRIBE_IMAGE_QUESTION),
        ("assistant", "A kitchen."),
        ("user", "Is the stove on?"),
        ("assistant", "No."),
    ]


def test_history_sent_to_model_is_capped_to_most_recent_eight_turns(client, fake_openai):
    session_id = start_session(client, fake_openai, description="Initial description.")
    for number in range(1, 5):
        ask(client, fake_openai, session_id, f"Question {number}", f"Answer {number}")

    ask(client, fake_openai, session_id, "Question 5", "Answer 5")

    # 2 turns from /describe + 8 from four follow-ups = 10 stored; only the last 8 go upstream.
    assert history_sent(fake_openai) == [
        turn for number in range(1, 5) for turn in (("user", f"Question {number}"), ("assistant", f"Answer {number}"))
    ]
    assert new_question_sent(fake_openai)["content"][0]["text"] == "Question 5"


def test_read_and_chat_sessions_support_follow_ups_too(client, fake_openai):
    fake_openai.will_answer("Exit 12A")
    read_session = client.post("/read", files=upload()).json()["sessionId"]
    fake_openai.will_answer("It is a road sign.")
    chat_session = client.post("/chat", files=upload(), data={"question": "What is this?"}).json()["sessionId"]

    ask(client, fake_openai, read_session, "Which exit?", "12A")
    read_history = history_sent(fake_openai)
    ask(client, fake_openai, chat_session, "What colour?", "Green")
    chat_history = history_sent(fake_openai)

    assert read_history == [("user", be_my_lens.READ_CONTENTS_QUESTION), ("assistant", "Exit 12A")]
    assert chat_history == [("user", "What is this?"), ("assistant", "It is a road sign.")]


def test_sessions_do_not_share_images_or_history(client, fake_openai):
    fake_openai.will_answer("A cat.")
    cat_session = client.post("/describe", files=upload(b"cat-image")).json()["sessionId"]
    fake_openai.will_answer("A dog.")
    client.post("/describe", files=upload(b"dog-image"))

    ask(client, fake_openai, cat_session, "What colour is it?", "Black.")

    assert history_sent(fake_openai)[-1] == ("assistant", "A cat.")
    image_url = new_question_sent(fake_openai)["content"][1]["image_url"]["url"]
    assert image_url == "data:image/jpeg;base64," + base64.b64encode(b"cat-image").decode()


def test_unknown_session_is_not_found(client, fake_openai):
    response = client.post("/followup", json={"sessionId": "does-not-exist", "question": "Hello?"})

    assert response.status_code == 404
    assert fake_openai.requests == []


def test_blank_question_is_rejected_and_not_stored(client, fake_openai):
    session_id = start_session(client, fake_openai, description="A desk.")

    rejected = client.post("/followup", json={"sessionId": session_id, "question": "   "})
    ask(client, fake_openai, session_id, "What is on it?", "A laptop.")

    assert rejected.status_code == 400
    assert history_sent(fake_openai) == [
        ("user", be_my_lens.DESCRIBE_IMAGE_QUESTION),
        ("assistant", "A desk."),
    ]


def test_failed_follow_up_leaves_conversation_intact_for_a_retry(client, fake_openai):
    session_id = start_session(client, fake_openai, description="A bus stop.")
    fake_openai.will_respond(503, text="upstream overloaded")
    failed = client.post("/followup", json={"sessionId": session_id, "question": "Which bus?"})

    retried = ask(client, fake_openai, session_id, "Which bus?", "Bus 7.")

    assert failed.status_code == 502
    assert retried.status_code == 200
    assert history_sent(fake_openai) == [
        ("user", be_my_lens.DESCRIBE_IMAGE_QUESTION),
        ("assistant", "A bus stop."),
    ]


def test_malformed_follow_up_body_is_rejected(client, fake_openai):
    response = client.post("/followup", json={"question": "No session id"})

    assert response.status_code == 422
    assert fake_openai.requests == []
