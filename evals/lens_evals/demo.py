"""Stubbed image -> response -> judge pipeline for previewing the harness UX.

The demo dataset (``demo/demo_cases.json``) is a normal dataset whose cases
also carry a ``stub`` block::

    "stub": {
      "latency_s": 1.2,                    # optional simulated model latency
      "response": "text the model 'said'", # or "target_error": "simulated failure"
      "judge": { ...raw judge output... }  # object or string, parsed by the real parse_verdict
    }

Stub blocks are only accepted here; ``load_dataset`` rejects them, so they
cannot leak into real datasets. Images are never opened in demo mode.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset import DatasetError, EvalCase, parse_dataset, read_json_file
from .judge import Verdict, parse_verdict
from .targets import TargetError

DEMO_DATASET = Path(__file__).resolve().parents[1] / "demo" / "demo_cases.json"
DEMO_MODEL_NAME = "stub-vision-model"
DEMO_JUDGE_NAME = "stub-judge"
DELAY_SCALE = 1.0  # multiply simulated latencies; tests set this to 0
JUDGE_LATENCY_S = 0.4

_STUB_KEYS = {"latency_s", "response", "target_error", "judge"}


@dataclass(frozen=True)
class StubEntry:
    response: str | None
    target_error: str | None
    judge: dict[str, Any] | str | None
    latency_s: float = 0.0


def load_demo(path: Path | str = DEMO_DATASET) -> tuple[list[EvalCase], dict[str, StubEntry]]:
    path = Path(path)
    data = read_json_file(path)

    stubs_raw: dict[int, Any] = {}
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        stripped = []
        for index, raw in enumerate(data["cases"]):
            if isinstance(raw, dict):
                raw = dict(raw)
                stubs_raw[index] = raw.pop("stub", None)
            stripped.append(raw)
        data = {**data, "cases": stripped}

    cases = parse_dataset(data, base_dir=path.parent)

    errors: list[str] = []
    stubs: dict[str, StubEntry] = {}
    for index, case in enumerate(cases):
        entry = _parse_stub(stubs_raw.get(index), f"cases[{index}] ('{case.id}')", errors)
        if entry:
            stubs[case.id] = entry
    if errors:
        raise DatasetError(errors)
    return cases, stubs


def _parse_stub(raw: Any, label: str, errors: list[str]) -> StubEntry | None:
    if not isinstance(raw, dict):
        errors.append(f"{label}: demo cases need a 'stub' object")
        return None
    problems = []
    unknown = sorted(set(raw) - _STUB_KEYS)
    if unknown:
        problems.append(f"unknown stub key(s) {', '.join(unknown)}")
    has_response, has_error = isinstance(raw.get("response"), str), isinstance(raw.get("target_error"), str)
    if has_response == has_error:
        problems.append("stub needs exactly one of 'response' or 'target_error'")
    if has_response and not isinstance(raw.get("judge"), (dict, str)):
        problems.append("stub with a 'response' needs a 'judge' output (object or string)")
    if has_error and "judge" in raw:
        problems.append("stub with a 'target_error' must not define 'judge' (the judge is never called)")
    latency = raw.get("latency_s", 0.0)
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0:
        problems.append("'latency_s' must be a non-negative number")
    if problems:
        errors.extend(f"{label}: {p}" for p in problems)
        return None
    return StubEntry(
        response=raw.get("response"),
        target_error=raw.get("target_error"),
        judge=raw.get("judge"),
        latency_s=float(latency),
    )


class StubTarget:
    def __init__(self, stubs: dict[str, StubEntry], name: str = DEMO_MODEL_NAME):
        self.name = name
        self._stubs = stubs

    async def respond(self, case: EvalCase) -> str:
        entry = self._stubs[case.id]
        await asyncio.sleep(entry.latency_s * DELAY_SCALE)
        if entry.target_error is not None:
            raise TargetError(entry.target_error)
        return entry.response


class StubJudge:
    def __init__(self, stubs: dict[str, StubEntry], name: str = DEMO_JUDGE_NAME):
        self.name = name
        self._stubs = stubs

    async def judge(self, case: EvalCase, response_text: str) -> Verdict:
        await asyncio.sleep(JUDGE_LATENCY_S * DELAY_SCALE)
        return parse_verdict(self._stubs[case.id].judge, case)
