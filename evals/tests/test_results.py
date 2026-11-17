"""Aggregation, exit codes and the machine-readable results file."""

import json
from datetime import datetime, timezone

from fakes import make_case, verdict_for

from lens_evals.dataset import Task
from lens_evals.results import RESULTS_SCHEMA_VERSION, CaseResult, CaseStatus, SuiteResult

DESCRIBE_OK = make_case("d-ok")
DESCRIBE_BAD = make_case("d-bad", must_include=("a crosswalk", "a red signal"), must_not_include=("safe",))
READ_OK = make_case("r-ok", task=Task.READ_TEXT, must_include=("EXIT",))
READ_ERR = make_case("r-err", task=Task.READ_TEXT, must_include=("EXIT",))


def passed(case):
    return CaseResult(case=case, status=CaseStatus.PASSED, response="ok", verdict=verdict_for(case), latency_s=1.25)


def failed(case, **kwargs):
    return CaseResult(case=case, status=CaseStatus.FAILED, response="meh", verdict=verdict_for(case, **kwargs), latency_s=2.0)


def errored(case):
    return CaseResult(case=case, status=CaseStatus.ERROR, error="TargetError: HTTP 429", error_stage="target")


def suite(*results):
    return SuiteResult(
        model="gpt-under-test",
        judge_model="gpt-judge",
        results=list(results),
        started_at=datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        duration_s=3.5,
        context={"locale": "ar", "mode": "live"},
    )


def test_summary_counts_and_pass_rate_over_scored_cases_only():
    s = suite(passed(DESCRIBE_OK), failed(DESCRIBE_BAD, missing=("a red signal",)), passed(READ_OK), errored(READ_ERR))
    summary = s.summary()

    assert (summary.total, summary.passed, summary.failed, summary.errors) == (4, 2, 1, 1)
    assert summary.scored == 3
    assert summary.pass_rate == 2 / 3


def test_pass_rate_is_none_when_nothing_could_be_scored():
    assert suite(errored(READ_ERR)).summary().pass_rate is None


def test_breakdown_by_task_in_task_order():
    s = suite(passed(READ_OK), failed(DESCRIBE_BAD), passed(DESCRIBE_OK), errored(READ_ERR))
    by_task = s.by_task()

    assert list(by_task) == [Task.DESCRIBE_IMAGE, Task.READ_TEXT]
    assert (by_task[Task.DESCRIBE_IMAGE].passed, by_task[Task.DESCRIBE_IMAGE].failed) == (1, 1)
    assert (by_task[Task.READ_TEXT].passed, by_task[Task.READ_TEXT].errors) == (1, 1)


def test_tasks_without_cases_are_omitted_from_the_breakdown():
    assert list(suite(passed(DESCRIBE_OK)).by_task()) == [Task.DESCRIBE_IMAGE]


def test_exit_code():
    assert suite(passed(DESCRIBE_OK), passed(READ_OK)).exit_code == 0
    assert suite(passed(DESCRIBE_OK), failed(DESCRIBE_BAD)).exit_code == 1
    assert suite(passed(DESCRIBE_OK), errored(READ_ERR)).exit_code == 1


def test_to_dict_is_json_serialisable_and_self_describing():
    s = suite(passed(DESCRIBE_OK), failed(DESCRIBE_BAD, missing=("a red signal",), forbidden=("safe",)), errored(READ_ERR))
    data = json.loads(json.dumps(s.to_dict()))

    assert data["schema_version"] == RESULTS_SCHEMA_VERSION
    assert data["run"]["model"] == "gpt-under-test"
    assert data["run"]["judge_model"] == "gpt-judge"
    assert data["run"]["started_at"] == "2025-01-02T03:04:05+00:00"
    assert data["run"]["locale"] == "ar"
    assert data["summary"]["passed"] == 1
    assert data["summary"]["by_task"]["describe_image"]["failed"] == 1

    ok, bad, err = data["results"]
    assert ok["id"] == "d-ok" and ok["status"] == "passed" and ok["score"] == 1
    assert bad["score"] == 0
    assert bad["missing"] == ["a red signal"]
    assert bad["forbidden_present"] == ["safe"]
    assert bad["checks"]["must_include"][1] == {"item": "a red signal", "present": False, "evidence": ""}
    assert err["status"] == "error" and err["score"] is None
    assert err["error_stage"] == "target" and "429" in err["error"]


def test_to_dict_image_paths_are_strings():
    data = suite(passed(DESCRIBE_OK)).to_dict()
    assert data["results"][0]["image"] == str(DESCRIBE_OK.image)
