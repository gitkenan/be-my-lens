"""Minimal OpenAI Responses API client: request shape, text extraction, retries."""

import asyncio
import json

import httpx
import pytest

from lens_evals.openai_client import OpenAIError, ResponsesClient, extract_output_text


def ok_body(text="hello"):
    return {
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ]
    }


async def no_sleep(_seconds):
    return None


def make_client(handler, **kwargs):
    return ResponsesClient(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        sleep=no_sleep,
        **kwargs,
    )


def run(coro):
    return asyncio.run(coro)


class TestExtractOutputText:
    def test_joins_all_output_text_chunks_from_message_items(self):
        data = {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "one"}]},
                {"type": "message", "content": [{"type": "output_text", "text": "two"}, {"type": "refusal"}]},
            ]
        }
        assert extract_output_text(data) == "one\ntwo"

    def test_ignores_non_message_items(self):
        assert extract_output_text(ok_body("only this")) == "only this"

    def test_empty_when_no_output(self):
        assert extract_output_text({}) == ""


def test_posts_payload_to_responses_endpoint_with_bearer_auth():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body("hi"))

    async def go():
        async with make_client(handler) as client:
            return await client.create({"model": "m", "input": []})

    data = run(go())

    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {"model": "m", "input": []}
    assert extract_output_text(data) == "hi"


def test_base_url_is_configurable():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ok_body())

    async def go():
        async with make_client(handler, base_url="http://proxy.local/v1/") as client:
            await client.create({})

    run(go())
    assert seen["url"] == "http://proxy.local/v1/responses"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_transient_http_errors_then_succeeds(status):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(status, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=ok_body("finally"))

    async def go():
        async with make_client(handler, max_retries=2) as client:
            return await client.create({})

    assert extract_output_text(run(go())) == "finally"
    assert len(calls) == 3


def test_gives_up_after_max_retries_with_the_api_error_message():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "Rate limit reached"}})

    async def go():
        async with make_client(handler, max_retries=1) as client:
            await client.create({})

    with pytest.raises(OpenAIError) as excinfo:
        run(go())
    assert len(calls) == 2
    assert excinfo.value.status_code == 429
    assert "Rate limit reached" in str(excinfo.value)


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "Invalid model 'nope'"}})

    async def go():
        async with make_client(handler, max_retries=3) as client:
            await client.create({})

    with pytest.raises(OpenAIError, match="Invalid model 'nope'"):
        run(go())
    assert len(calls) == 1


def test_non_json_error_bodies_are_reported():
    def handler(request):
        return httpx.Response(401, text="unauthorised")

    async def go():
        async with make_client(handler) as client:
            await client.create({})

    with pytest.raises(OpenAIError, match="401.*unauthorised"):
        run(go())


def test_retries_network_errors():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json=ok_body("recovered"))

    async def go():
        async with make_client(handler, max_retries=1) as client:
            return await client.create({})

    assert extract_output_text(run(go())) == "recovered"


def test_network_errors_become_openai_errors_after_retries():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    async def go():
        async with make_client(handler, max_retries=1) as client:
            await client.create({})

    with pytest.raises(OpenAIError, match="no route"):
        run(go())


def test_backoff_grows_between_attempts():
    delays = []

    async def record_sleep(seconds):
        delays.append(seconds)

    def handler(request):
        return httpx.Response(503, json={})

    async def go():
        client = ResponsesClient(
            api_key="k", transport=httpx.MockTransport(handler), sleep=record_sleep, max_retries=3, backoff_s=1.0
        )
        async with client:
            await client.create({})

    with pytest.raises(OpenAIError):
        run(go())
    assert delays == [1.0, 2.0, 4.0]
