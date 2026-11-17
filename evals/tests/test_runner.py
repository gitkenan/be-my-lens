"""Running a suite: target -> judge -> CaseResult, with concurrency and progress callbacks."""

import asyncio

import pytest
from fakes import FakeJudge, FakeTarget, make_case, verdict_for

from lens_evals.judge import JudgeError
from lens_evals.results import CaseStatus
from lens_evals.runner import run_suite
from lens_evals.targets import TargetError

PASSING = make_case("passing", must_include=("a crosswalk",))
MISSING = make_case("missing", must_include=("a crosswalk", "a red signal"))
FORBIDDEN = make_case("forbidden", must_include=("a crosswalk",), must_not_include=("says it is safe",))


def run(cases, target, judge, **kwargs):
    return asyncio.run(run_suite(cases, target, judge, **kwargs))


def test_classifies_pass_and_fail_from_the_judge_score():
    target = FakeTarget({c.id: f"response for {c.id}" for c in (PASSING, MISSING, FORBIDDEN)})
    judge = FakeJudge(
        {
            "passing": verdict_for(PASSING),
            "missing": verdict_for(MISSING, missing=("a red signal",)),
            "forbidden": verdict_for(FORBIDDEN, forbidden=("says it is safe",)),
        }
    )

    suite = run([PASSING, MISSING, FORBIDDEN], target, judge)

    assert [r.status for r in suite.results] == [CaseStatus.PASSED, CaseStatus.FAILED, CaseStatus.FAILED]
    assert [r.score for r in suite.results] == [1, 0, 0]
    assert suite.results[1].verdict.missing == ("a red signal",)
    assert suite.results[2].verdict.forbidden_present == ("says it is safe",)


def test_judge_receives_the_exact_target_response():
    target = FakeTarget({"passing": "A zebra crossing."})
    judge = FakeJudge({"passing": verdict_for(PASSING)})

    suite = run([PASSING], target, judge)

    assert judge.calls == [("passing", "A zebra crossing.")]
    assert suite.results[0].response == "A zebra crossing."


def test_target_failure_is_an_error_and_skips_the_judge():
    target = FakeTarget({"passing": TargetError("HTTP 429")})
    judge = FakeJudge({})

    result = run([PASSING], target, judge).results[0]

    assert result.status is CaseStatus.ERROR
    assert result.error_stage == "target"
    assert "HTTP 429" in result.error
    assert result.score is None
    assert judge.calls == []


def test_judge_failure_is_an_error_that_keeps_the_response():
    target = FakeTarget({"passing": "A crosswalk."})
    judge = FakeJudge({"passing": JudgeError("not JSON")})

    result = run([PASSING], target, judge).results[0]

    assert result.status is CaseStatus.ERROR
    assert result.error_stage == "judge"
    assert result.response == "A crosswalk."
    assert "not JSON" in result.error


def test_unexpected_exceptions_do_not_abort_the_suite():
    target = FakeTarget({"passing": ValueError("boom"), "missing": "fine"})
    judge = FakeJudge({"missing": verdict_for(MISSING)})

    suite = run([PASSING, MISSING], target, judge)

    assert [r.status for r in suite.results] == [CaseStatus.ERROR, CaseStatus.PASSED]
    assert "ValueError" in suite.results[0].error


def test_results_keep_dataset_order_even_when_cases_finish_out_of_order():
    cases = [make_case(f"c{i}") for i in range(4)]
    target = FakeTarget({c.id: "x" for c in cases}, delays={"c0": 0.05, "c1": 0.0, "c2": 0.03, "c3": 0.01})
    judge = FakeJudge({c.id: verdict_for(c) for c in cases})
    finished = []

    suite = run(cases, target, judge, concurrency=4, on_result=lambda r: finished.append(r.case.id))

    assert [r.case.id for r in suite.results] == ["c0", "c1", "c2", "c3"]
    assert finished != ["c0", "c1", "c2", "c3"]
    assert sorted(finished) == ["c0", "c1", "c2", "c3"]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_concurrency_limit_is_respected(limit):
    cases = [make_case(f"c{i}") for i in range(6)]
    target = FakeTarget({c.id: "x" for c in cases}, delays={c.id: 0.01 for c in cases})
    judge = FakeJudge({c.id: verdict_for(c) for c in cases})

    run(cases, target, judge, concurrency=limit)

    assert target.max_in_flight == limit


def test_rejects_non_positive_concurrency():
    with pytest.raises(ValueError):
        run([PASSING], FakeTarget({}), FakeJudge({}), concurrency=0)


def test_on_start_and_on_result_are_called_once_per_case():
    cases = [make_case(f"c{i}") for i in range(3)]
    target = FakeTarget({c.id: "x" for c in cases})
    judge = FakeJudge({c.id: verdict_for(c) for c in cases})
    started, finished = [], []

    run(cases, target, judge, on_start=lambda c: started.append(c.id), on_result=lambda r: finished.append(r.case.id))

    assert sorted(started) == ["c0", "c1", "c2"]
    assert sorted(finished) == ["c0", "c1", "c2"]


def test_suite_records_model_judge_timing_and_context():
    target = FakeTarget({"passing": "x"}, name="gpt-under-test")
    judge = FakeJudge({"passing": verdict_for(PASSING)}, name="gpt-judge")

    suite = run([PASSING], target, judge, context={"locale": "ar"})

    assert suite.model == "gpt-under-test"
    assert suite.judge_model == "gpt-judge"
    assert suite.context == {"locale": "ar"}
    assert suite.duration_s >= 0
    assert suite.results[0].latency_s >= 0
    assert suite.started_at.tzinfo is not None


@pytest.mark.parametrize(
    "exc, expected",
    [
        (TargetError("Model returned no text."), "Model returned no text."),
        (JudgeError("Judge score 1 contradicts its own item checks"), "Judge score 1 contradicts its own item checks"),
    ],
)
def test_known_error_types_are_reported_without_a_redundant_class_prefix(exc, expected):
    result = run([PASSING], FakeTarget({"passing": exc}), FakeJudge({})).results[0]
    assert result.error == expected


def test_openai_errors_are_reported_without_a_class_prefix():
    from lens_evals.openai_client import OpenAIError

    result = run([PASSING], FakeTarget({"passing": OpenAIError("OpenAI returned HTTP 429: slow down", 429)}), FakeJudge({})).results[0]
    assert result.error == "OpenAI returned HTTP 429: slow down"
