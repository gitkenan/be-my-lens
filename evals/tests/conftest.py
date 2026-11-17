"""Shared fixtures for the eval harness unit tests.

These tests must never reach a real LLM. Every HTTP interaction goes through
``httpx.MockTransport``; as a safety net, raw socket connections are blocked.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from lens_evals.dataset import Task
from lens_evals.prompts import TaskPrompt


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def guard(*_args, **_kwargs):
        raise RuntimeError("Network access is disabled in eval unit tests.")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def _isolated_temp_dir(tmp_path, monkeypatch):
    """Full reports default to the system temp dir; keep tests from writing to the real /tmp."""
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "system-tmp"))
    (tmp_path / "system-tmp").mkdir()


@pytest.fixture
def write_json(tmp_path):
    def _write(data, name: str = "cases.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def fake_prompts() -> dict[Task, TaskPrompt]:
    return {
        Task.DESCRIBE_IMAGE: TaskPrompt(
            task=Task.DESCRIBE_IMAGE,
            developer_prompt="DESCRIBE-DEV-PROMPT",
            user_question="DESCRIBE-QUESTION",
        ),
        Task.READ_TEXT: TaskPrompt(
            task=Task.READ_TEXT,
            developer_prompt="READ-DEV-PROMPT",
            user_question="READ-QUESTION",
        ),
    }
