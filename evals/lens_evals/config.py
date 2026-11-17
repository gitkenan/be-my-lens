"""Environment-driven settings.

* ``EVAL_JUDGE_MODEL`` - the judge LLM (an env var, so it stays fixed across runs).
* ``OPENAI_API_KEY``   - shared with the backend.

The model under test is *not* configured here: it is a CLI flag (``--model``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

JUDGE_MODEL_ENV = "EVAL_JUDGE_MODEL"
API_KEY_ENV = "OPENAI_API_KEY"


class ConfigError(RuntimeError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing required environment variable(s): {', '.join(missing)}")


@dataclass(frozen=True)
class Settings:
    judge_model: str
    api_key: str = field(repr=False)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    environ = os.environ if environ is None else environ
    values = {name: (environ.get(name) or "").strip() for name in (JUDGE_MODEL_ENV, API_KEY_ENV)}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(missing)
    return Settings(judge_model=values[JUDGE_MODEL_ENV], api_key=values[API_KEY_ENV])
