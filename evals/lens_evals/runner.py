"""Runs eval cases through a target and a judge.

One ``run_suite`` call evaluates one model (target) with one judge. Running
several models later means calling it once per target and comparing the
resulting ``SuiteResult`` objects; the runner itself does not need to change.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from .dataset import EvalCase
from .judge import Judge, JudgeError
from .openai_client import OpenAIError
from .results import CaseResult, CaseStatus, SuiteResult
from .targets import Target, TargetError

DEFAULT_CONCURRENCY = 4

# The harness's own errors already read as sentences; the stage says where they happened.
_SELF_DESCRIBING = (TargetError, JudgeError, OpenAIError)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, _SELF_DESCRIBING):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"  # unexpected bugs keep their type for debugging


async def evaluate_case(case: EvalCase, target: Target, judge: Judge) -> CaseResult:
    started = time.perf_counter()
    try:
        response = await target.respond(case)
    except Exception as exc:  # noqa: BLE001 - one bad case must not abort the suite
        return CaseResult(
            case=case,
            status=CaseStatus.ERROR,
            error=_describe(exc),
            error_stage="target",
            latency_s=time.perf_counter() - started,
        )
    latency = time.perf_counter() - started

    try:
        verdict = await judge.judge(case, response)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            case=case,
            status=CaseStatus.ERROR,
            response=response,
            error=_describe(exc),
            error_stage="judge",
            latency_s=latency,
        )

    return CaseResult(
        case=case,
        status=CaseStatus.PASSED if verdict.passed else CaseStatus.FAILED,
        response=response,
        verdict=verdict,
        latency_s=latency,
    )


async def run_suite(
    cases: Sequence[EvalCase],
    target: Target,
    judge: Judge,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_start: Callable[[EvalCase], None] | None = None,
    on_result: Callable[[CaseResult], None] | None = None,
    context: Mapping[str, str] | None = None,
) -> SuiteResult:
    """Evaluate ``cases`` with at most ``concurrency`` in flight; results keep dataset order."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = asyncio.Semaphore(concurrency)
    started_at = datetime.now(timezone.utc)
    clock_start = time.perf_counter()

    async def worker(case: EvalCase) -> CaseResult:
        async with semaphore:
            if on_start:
                on_start(case)
            result = await evaluate_case(case, target, judge)
        if on_result:
            on_result(result)
        return result

    results = await asyncio.gather(*(worker(case) for case in cases))

    return SuiteResult(
        model=target.name,
        judge_model=judge.name,
        results=list(results),
        started_at=started_at,
        duration_s=time.perf_counter() - clock_start,
        context=dict(context or {}),
    )
