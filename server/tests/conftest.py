"""Fixtures for the backend suite.

The tests drive the real FastAPI app over HTTP (``TestClient``) and replace only the
outermost boundary: the network hop to OpenAI. Everything in between (validation,
prompt selection, payload construction, status handling, response parsing and the
in-memory session store) runs for real.
"""

import functools
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

import app as be_my_lens
from support import TEST_API_KEY, FakeOpenAI

API_CONTRACT_PATH = SERVER_DIR.parent / "contract" / "api-contract.json"


@pytest.fixture(autouse=True)
def fake_openai(monkeypatch) -> FakeOpenAI:
    """Autouse, so no test in this suite can reach the real OpenAI API."""
    fake = FakeOpenAI()
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        functools.partial(real_async_client, transport=httpx.MockTransport(fake.handle)),
    )
    # Never forward a developer's real key (load_dotenv may have read server/.env).
    monkeypatch.setattr(be_my_lens, "OPENAI_API_KEY", TEST_API_KEY)
    yield fake
    assert not fake.unexpected_requests, (
        "the app called OpenAI without the test queueing a reply: "
        f"{[str(request.url) for request in fake.unexpected_requests]}"
    )


@pytest.fixture(autouse=True)
def clean_sessions():
    be_my_lens.SESSIONS.clear()
    yield
    be_my_lens.SESSIONS.clear()


@pytest.fixture
def client() -> TestClient:
    # Behave like a deployed server: unhandled errors become HTTP 500 responses
    # instead of exceptions re-raised into the test.
    return TestClient(be_my_lens.app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def api_contract() -> dict:
    """Endpoint shapes shared with the Android client tests (contract/api-contract.json)."""
    return json.loads(API_CONTRACT_PATH.read_text(encoding="utf-8"))["endpoints"]
