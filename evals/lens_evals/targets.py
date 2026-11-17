"""The model under test ("target").

A ``Target`` turns an eval case into the text a user would hear. The production
target replays the backend's request for /describe and /read with a
configurable model. Other targets can implement the same protocol, e.g. the
demo ``StubTarget``, or in future an HTTP target that calls a deployed backend.

Multi-model runs are expected to be "one Target per model": the runner takes a
single target and reports under ``target.name``, so comparing models means
running the same cases through several targets.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Protocol, runtime_checkable

from .dataset import EvalCase, Task
from .openai_client import ResponsesClient, extract_output_text
from .prompts import TaskPrompt


class TargetError(RuntimeError):
    """The model under test did not produce a usable response."""


@runtime_checkable
class Target(Protocol):
    name: str

    async def respond(self, case: EvalCase) -> str: ...


def image_to_data_url(path: Path) -> str:
    """Encode an image the way the backend does (``data:<mime>;base64,...``, JPEG fallback)."""
    if not path.is_file():
        raise TargetError(f"Image not found: {path}")
    content = path.read_bytes()
    if not content:
        raise TargetError(f"Image file is empty: {path}")
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


class OpenAIVisionTarget:
    """Sends the same Responses API payload as ``server/app.py::ask_model``."""

    def __init__(self, client: ResponsesClient, model: str, prompts: dict[Task, TaskPrompt]):
        self.name = model
        self._client = client
        self._model = model
        self._prompts = prompts

    def build_payload(self, case: EvalCase) -> dict:
        prompt = self._prompts[case.task]
        return {
            "model": self._model,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": prompt.developer_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt.user_question},
                        {"type": "input_image", "image_url": image_to_data_url(case.image), "detail": "high"},
                    ],
                },
            ],
        }

    async def respond(self, case: EvalCase) -> str:
        data = await self._client.create(self.build_payload(case))
        text = extract_output_text(data).strip()
        if not text:
            raise TargetError("Model returned no text.")
        return text
