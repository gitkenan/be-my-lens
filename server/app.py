import base64
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_RESPONSES_API_URL = "https://api.openai.com/v1/responses"
OPENAI_CHAT_COMPLETIONS_API_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_LOCALE = os.getenv("PROMPT_LOCALE", "ar").strip() or "ar"
PROMPTS_DIR = Path(__file__).parent / "prompts" / PROMPT_LOCALE
if not PROMPTS_DIR.exists():
    PROMPTS_DIR = Path(__file__).parent / "prompts" / "en"

DESCRIBE_IMAGE_PROMPT = (PROMPTS_DIR / "describe_image.txt").read_text(encoding="utf-8").strip()
READ_CONTENTS_PROMPT = (PROMPTS_DIR / "read_contents.txt").read_text(encoding="utf-8").strip()
ASK_QUESTION_PROMPT = (PROMPTS_DIR / "ask_question.txt").read_text(encoding="utf-8").strip()
DESCRIBE_IMAGE_QUESTION = "صف هذه الصورة لمستخدم كفيف أو ضعيف البصر."
READ_CONTENTS_QUESTION = "اقرأ النص الموجود في الصورة."


@dataclass
class ChatTurn:
    role: str
    text: str


@dataclass
class Session:
    image_data_url: str
    transcript: List[ChatTurn] = field(default_factory=list)


class FollowUpBody(BaseModel):
    sessionId: str
    question: str


app = FastAPI(title="Be My Lens API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: dict[str, Session] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/describe")
async def describe(image: UploadFile = File(...)) -> dict[str, str]:
    ensure_api_key()
    content = await read_image_payload(image)

    image_data_url = to_data_url(content, image.content_type or "image/jpeg")
    answer = await ask_model(
        image_data_url=image_data_url,
        developer_prompt=DESCRIBE_IMAGE_PROMPT,
        user_question=DESCRIBE_IMAGE_QUESTION,
    )

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = Session(
        image_data_url=image_data_url,
        transcript=[
            ChatTurn(role="user", text=DESCRIBE_IMAGE_QUESTION),
            ChatTurn(role="assistant", text=answer),
        ],
    )
    return {"sessionId": session_id, "description": answer}


@app.post("/read")
async def read_contents(image: UploadFile = File(...)) -> dict[str, str]:
    ensure_api_key()
    content = await read_image_payload(image)

    image_data_url = to_data_url(content, image.content_type or "image/jpeg")
    answer = await ask_model(
        image_data_url=image_data_url,
        developer_prompt=READ_CONTENTS_PROMPT,
        user_question=READ_CONTENTS_QUESTION,
    )

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = Session(
        image_data_url=image_data_url,
        transcript=[
            ChatTurn(role="user", text=READ_CONTENTS_QUESTION),
            ChatTurn(role="assistant", text=answer),
        ],
    )
    return {"sessionId": session_id, "contents": answer}


@app.post("/chat")
async def chat(image: UploadFile = File(...), question: str = Form(...)) -> dict[str, str]:
    ensure_api_key()
    content = await read_image_payload(image)

    clean_question = question.strip()
    if not clean_question:
        raise HTTPException(status_code=400, detail="يجب ألا يكون السؤال فارغا.")

    image_data_url = to_data_url(content, image.content_type or "image/jpeg")
    answer = await ask_chat_model(
        image_data_url=image_data_url,
        user_question=clean_question,
        transcript=[],
    )

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = Session(
        image_data_url=image_data_url,
        transcript=[
            ChatTurn(role="user", text=clean_question),
            ChatTurn(role="assistant", text=answer),
        ],
    )
    return {"sessionId": session_id, "answer": answer}


@app.post("/followup")
async def followup(body: FollowUpBody) -> dict[str, str]:
    ensure_api_key()
    session = SESSIONS.get(body.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="لم يتم العثور على الجلسة.")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="يجب ألا يكون السؤال فارغا.")

    answer = await ask_chat_model(
        image_data_url=session.image_data_url,
        user_question=question,
        transcript=session.transcript,
    )
    session.transcript.extend(
        [
            ChatTurn(role="user", text=question),
            ChatTurn(role="assistant", text=answer),
        ]
    )
    return {"answer": answer}


def ensure_api_key() -> None:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="متغير OPENAI_API_KEY غير مضبوط.")


def to_data_url(content: bytes, content_type: str) -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


async def read_image_payload(image: UploadFile) -> bytes:
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="ملف الصورة فارغ.")
    return content


async def ask_model(image_data_url: str, developer_prompt: str, user_question: str) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": developer_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_question,
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "high",
                    },
                ],
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(OPENAI_RESPONSES_API_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=response.text)

    data = response.json()
    text = extract_output_text(data)
    if not text:
        raise HTTPException(status_code=502, detail="لم يرجع النموذج أي نص.")
    return text.strip()


async def ask_chat_model(
    image_data_url: str,
    user_question: str,
    transcript: List[ChatTurn],
) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "messages": build_chat_messages(
            image_data_url=image_data_url,
            user_question=user_question,
            transcript=transcript,
        ),
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(OPENAI_CHAT_COMPLETIONS_API_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=response.text)

    data = response.json()
    text = extract_chat_output_text(data)
    if not text:
        raise HTTPException(status_code=502, detail="لم يرجع النموذج أي نص.")
    return text.strip()


def build_chat_messages(
    image_data_url: str,
    user_question: str,
    transcript: List[ChatTurn],
) -> List[dict]:
    messages: List[dict] = [
        {
            "role": "developer",
            "content": ASK_QUESTION_PROMPT,
        }
    ]

    for turn in transcript[-8:]:
        messages.append(
            {
                "role": turn.role,
                "content": turn.text,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_question,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url,
                        "detail": "high",
                    },
                },
            ],
        }
    )
    return messages


def extract_output_text(data: dict) -> str:
    output = data.get("output", [])
    chunks: List[str] = []

    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text")
                if text:
                    chunks.append(text)

    return "\n".join(chunks)


def extract_chat_output_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks = []
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                chunks.append(item["text"])
        return "\n".join(chunks)

    return ""
