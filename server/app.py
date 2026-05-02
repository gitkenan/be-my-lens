import base64
import os
import uuid
from dataclasses import dataclass, field
from typing import List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_API_URL = "https://api.openai.com/v1/responses"

DEVELOPER_PROMPT = (
    "You are assisting a blind or low-vision user. "
    "Describe the image clearly and directly. "
    "Prioritize visible text, important objects, colors, layout, and safety-relevant details. "
    "If the user asks a follow-up question, answer it specifically using the same image context. "
    "If you are uncertain, say so."
)


@dataclass
class Session:
    image_data_url: str
    transcript: List[str] = field(default_factory=list)


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
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Image payload was empty.")

    image_data_url = to_data_url(content, image.content_type or "image/jpeg")
    answer = await ask_model(
        image_data_url=image_data_url,
        user_question="Describe this image for a blind or low-vision user.",
        transcript=[],
    )

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = Session(
        image_data_url=image_data_url,
        transcript=[
            "User: Describe this image for a blind or low-vision user.",
            f"Assistant: {answer}",
        ],
    )
    return {"sessionId": session_id, "description": answer}


@app.post("/followup")
async def followup(body: FollowUpBody) -> dict[str, str]:
    ensure_api_key()
    session = SESSIONS.get(body.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be blank.")

    answer = await ask_model(
        image_data_url=session.image_data_url,
        user_question=question,
        transcript=session.transcript,
    )
    session.transcript.extend(
        [
            f"User: {question}",
            f"Assistant: {answer}",
        ]
    )
    return {"answer": answer}


def ensure_api_key() -> None:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")


def to_data_url(content: bytes, content_type: str) -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def build_user_prompt(question: str, transcript: List[str]) -> str:
    if not transcript:
        return question

    history = "\n".join(transcript[-8:])
    return (
        "Use the same image as before.\n\n"
        f"Conversation so far:\n{history}\n\n"
        f"Latest user question: {question}"
    )


async def ask_model(image_data_url: str, user_question: str, transcript: List[str]) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": DEVELOPER_PROMPT,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_user_prompt(user_question, transcript),
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
        response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=response.text)

    data = response.json()
    text = extract_output_text(data)
    if not text:
        raise HTTPException(status_code=502, detail="The model returned no text output.")
    return text.strip()


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
