"""Start-up configuration the deployment relies on (.env / docker-compose env_file)."""

import importlib.util
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from support import upload

SERVER_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = SERVER_DIR / "prompts"


@pytest.fixture
def load_service(monkeypatch):
    """Import a fresh copy of app.py under the given environment, as a new process would."""
    access_logger = logging.getLogger("uvicorn.access")
    original_filters = list(access_logger.filters)

    def load(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        spec = importlib.util.spec_from_file_location("be_my_lens_fresh", SERVER_DIR / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    yield load
    access_logger.filters[:] = original_filters


def read_prompt(locale: str, name: str) -> str:
    return (PROMPTS_DIR / locale / name).read_text(encoding="utf-8").strip()


def test_health_check_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# (module constant, prompt file) for every prompt the service loads.
LOADED_PROMPTS = [
    ("DESCRIBE_IMAGE_PROMPT", "describe_image.txt"),
    ("READ_CONTENTS_PROMPT", "read_contents.txt"),
    ("ASK_QUESTION_PROMPT", "ask_question.txt"),
    ("TRANSLATE_TEXT_PROMPT", "translate_text.txt"),
]


def test_service_uses_the_arabic_prompts(load_service):
    service = load_service()

    for constant, file_name in LOADED_PROMPTS:
        assert read_prompt("ar", file_name), f"prompts/ar/{file_name} is empty"
        assert getattr(service, constant) == read_prompt("ar", file_name)


@pytest.mark.parametrize("stale_value", ["en", "xx"])
def test_stale_prompt_locale_setting_cannot_switch_language(load_service, stale_value):
    # Production .env files still carry PROMPT_LOCALE from when it was a setting.
    service = load_service(PROMPT_LOCALE=stale_value)

    for constant, file_name in LOADED_PROMPTS:
        assert getattr(service, constant) == read_prompt("ar", file_name)


def test_configured_model_and_key_are_used_for_model_calls(load_service, fake_openai):
    service = load_service(OPENAI_API_KEY="sk-from-env", OPENAI_MODEL="gpt-test-model")
    fake_openai.will_answer("answer")

    response = TestClient(service.app).post("/describe", files=upload())

    assert response.status_code == 200
    assert fake_openai.last_call["model"] == "gpt-test-model"
    assert fake_openai.requests[-1].headers["Authorization"] == "Bearer sk-from-env"


@pytest.mark.parametrize(
    "path, kept",
    [
        ("/health", True),
        ("/describe", True),
        ("/followup/", True),
        ("/translate_text?lang=ar", True),
        ("/wp-login.php", False),
        ("/.env", False),
        ("/", False),
    ],
)
def test_access_log_keeps_only_this_services_endpoints(caplog, path, kept):
    caplog.set_level(logging.INFO, logger="uvicorn.access")

    # Same call shape uvicorn uses for its access log lines.
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "203.0.113.7:51234", "GET", path, "1.1", 200)

    assert any(path in record.getMessage() for record in caplog.records) == kept
