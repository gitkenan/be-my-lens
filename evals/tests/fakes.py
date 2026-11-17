"""Test helpers: a case factory and in-memory Target / Judge doubles."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from lens_evals.dataset import EvalCase, Task
from lens_evals.judge import Check, Verdict


def make_case(
    case_id: str = "crosswalk",
    task: Task = Task.DESCRIBE_IMAGE,
    must_include: tuple[str, ...] = ("a pedestrian crosswalk",),
    must_not_include: tuple[str, ...] = (),
    image: Path = Path("/nonexistent/image.jpg"),
) -> EvalCase:
    return EvalCase(
        id=case_id,
        task=task,
        image=image,
        must_include=must_include,
        must_not_include=must_not_include,
    )


def verdict_for(case: EvalCase, missing=(), forbidden=(), reason="") -> Verdict:
    include = tuple(Check(item, item not in missing, "quote" if item not in missing else "") for item in case.must_include)
    exclude = tuple(Check(item, item in forbidden, "quote" if item in forbidden else "") for item in case.must_not_include)
    score = int(not missing and not forbidden)
    return Verdict(score=score, must_include=include, must_not_include=exclude, reason=reason)


class FakeTarget:
    """Returns ``responses[case.id]``; raises it if it is an exception. Optional per-case delays."""

    def __init__(self, responses, name="fake-model", delays=None):
        self.name = name
        self.responses = responses
        self.delays = delays or {}
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def respond(self, case):
        self.calls.append(case.id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays.get(case.id, 0))
            outcome = self.responses[case.id]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        finally:
            self.in_flight -= 1


class FakeJudge:
    """Returns ``verdicts[case.id]`` (a Verdict, or an exception to raise)."""

    def __init__(self, verdicts, name="fake-judge"):
        self.name = name
        self.verdicts = verdicts
        self.calls: list[tuple[str, str]] = []

    async def judge(self, case, response_text):
        self.calls.append((case.id, response_text))
        outcome = self.verdicts[case.id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Stream(io.StringIO):
    """A text stream with a configurable encoding and tty flag."""

    def __init__(self, encoding="utf-8", tty=False):
        super().__init__()
        self._encoding = encoding
        self._tty = tty

    @property
    def encoding(self):
        return self._encoding

    def isatty(self):
        return self._tty
