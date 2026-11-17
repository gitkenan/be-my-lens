"""Result types, aggregation and the JSON results file."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable

from .dataset import EvalCase, Task
from .judge import Verdict

RESULTS_SCHEMA_VERSION = 1


class CaseStatus(str, Enum):
    PASSED = "passed"  # judge score 1
    FAILED = "failed"  # judge score 0
    ERROR = "error"  # no score: the target or the judge failed


@dataclass(frozen=True)
class CaseResult:
    case: EvalCase
    status: CaseStatus
    response: str | None = None
    verdict: Verdict | None = None
    error: str | None = None
    error_stage: str | None = None  # "target" | "judge"
    latency_s: float = 0.0  # time for the model under test to respond

    @property
    def score(self) -> int | None:
        return self.verdict.score if self.verdict else None

    def to_dict(self) -> dict[str, Any]:
        verdict = self.verdict
        return {
            "id": self.case.id,
            "task": self.case.task.value,
            "image": str(self.case.image),
            "status": self.status.value,
            "score": self.score,
            "latency_s": round(self.latency_s, 3),
            "response": self.response,
            "missing": list(verdict.missing) if verdict else [],
            "forbidden_present": list(verdict.forbidden_present) if verdict else [],
            "reason": verdict.reason if verdict else None,
            "checks": {
                key: [{"item": c.item, "present": c.present, "evidence": c.evidence} for c in checks]
                for key, checks in (
                    ("must_include", verdict.must_include if verdict else ()),
                    ("must_not_include", verdict.must_not_include if verdict else ()),
                )
            },
            "error": self.error,
            "error_stage": self.error_stage,
        }


@dataclass(frozen=True)
class Summary:
    total: int
    passed: int
    failed: int
    errors: int

    @property
    def scored(self) -> int:
        return self.passed + self.failed

    @property
    def pass_rate(self) -> float | None:
        """Share of *scored* cases that passed. Errors are reported separately, not counted as failures."""
        return self.passed / self.scored if self.scored else None

    @classmethod
    def of(cls, results: Iterable[CaseResult]) -> "Summary":
        statuses = [r.status for r in results]
        return cls(
            total=len(statuses),
            passed=statuses.count(CaseStatus.PASSED),
            failed=statuses.count(CaseStatus.FAILED),
            errors=statuses.count(CaseStatus.ERROR),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "pass_rate": self.pass_rate,
        }


@dataclass
class SuiteResult:
    """All results of one model under test, graded by one judge."""

    model: str
    judge_model: str
    results: list[CaseResult]
    started_at: datetime
    duration_s: float
    context: dict[str, str] = field(default_factory=dict)  # e.g. locale, dataset, mode

    def summary(self) -> Summary:
        return Summary.of(self.results)

    def by_task(self) -> dict[Task, Summary]:
        return {
            task: Summary.of(r for r in self.results if r.case.task is task)
            for task in Task
            if any(r.case.task is task for r in self.results)
        }

    @property
    def exit_code(self) -> int:
        return 0 if all(r.status is CaseStatus.PASSED for r in self.results) else 1

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary().to_dict()
        summary["by_task"] = {task.value: s.to_dict() for task, s in self.by_task().items()}
        return {
            "schema_version": RESULTS_SCHEMA_VERSION,
            "run": {
                "model": self.model,
                "judge_model": self.judge_model,
                "started_at": self.started_at.isoformat(),
                "duration_s": round(self.duration_s, 3),
                **self.context,
            },
            "summary": summary,
            "results": [r.to_dict() for r in self.results],
        }
