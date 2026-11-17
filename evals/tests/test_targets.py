"""The model under test: requests must mirror what the backend sends for /describe and /read."""

import asyncio
import base64
import json

import httpx
import pytest
from fakes import make_case

from lens_evals.dataset import Task
from lens_evals.openai_client import ResponsesClient
from lens_evals.targets import OpenAIVisionTarget, Target, TargetError, image_to_data_url

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


def response_with(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


def make_target(fake_prompts, handler, model="gpt-test-vision"):
    client = ResponsesClient(api_key="sk", transport=httpx.MockTransport(handler))
    return OpenAIVisionTarget(client=client, model=model, prompts=fake_prompts), client


def run_target(target, client, case):
    async def go():
        async with client:
            return await target.respond(case)

    return asyncio.run(go())


@pytest.mark.parametrize(
    "name, mime",
    [("photo.png", "image/png"), ("photo.JPG", "image/jpeg"), ("photo.webp", "image/webp"), ("photo.unknownext", "image/jpeg")],
)
def test_image_to_data_url_uses_mime_type_from_extension(tmp_path, name, mime):
    path = tmp_path / name
    path.write_bytes(PNG_BYTES)
    assert image_to_data_url(path) == f"data:{mime};base64,{base64.b64encode(PNG_BYTES).decode()}"


def test_image_to_data_url_rejects_empty_files(tmp_path):
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    with pytest.raises(TargetError, match="empty"):
        image_to_data_url(path)


def test_target_name_is_the_model_under_test(fake_prompts):
    target, _ = make_target(fake_prompts, lambda r: httpx.Response(200, json={}), model="gpt-4.1-mini")
    assert target.name == "gpt-4.1-mini"
    assert isinstance(target, Target)


@pytest.mark.parametrize(
    "task, dev_prompt, question",
    [
        (Task.DESCRIBE_IMAGE, "DESCRIBE-DEV-PROMPT", "DESCRIBE-QUESTION"),
        (Task.READ_TEXT, "READ-DEV-PROMPT", "READ-QUESTION"),
    ],
)
def test_request_mirrors_the_backend_payload(tmp_path, fake_prompts, task, dev_prompt, question):
    image = tmp_path / "img.png"
    image.write_bytes(PNG_BYTES)
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=response_with("  A red stop sign.  "))

    target, client = make_target(fake_prompts, handler, model="model-from-flag")
    text = run_target(target, client, make_case(task=task, image=image))

    assert text == "A red stop sign."
    assert seen["body"] == {
        "model": "model-from-flag",
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": dev_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": question},
                    {"type": "input_image", "image_url": image_to_data_url(image), "detail": "high"},
                ],
            },
        ],
    }


def test_empty_model_output_is_an_error(tmp_path, fake_prompts):
    image = tmp_path / "img.png"
    image.write_bytes(PNG_BYTES)
    target, client = make_target(fake_prompts, lambda r: httpx.Response(200, json=response_with("   ")))

    with pytest.raises(TargetError, match="no text"):
        run_target(target, client, make_case(image=image))


def test_missing_image_is_an_error(tmp_path, fake_prompts):
    target, client = make_target(fake_prompts, lambda r: httpx.Response(200, json=response_with("x")))
    with pytest.raises(TargetError, match="not found"):
        run_target(target, client, make_case(image=tmp_path / "nope.jpg"))
