"""The stubbed demo pipeline and its committed fake data."""

import asyncio

import pytest
from fakes import make_case

from lens_evals import demo
from lens_evals.dataset import DatasetError, Task, load_dataset
from lens_evals.judge import Judge, JudgeError
from lens_evals.results import CaseStatus
from lens_evals.runner import run_suite
from lens_evals.targets import Target, TargetError


@pytest.fixture(autouse=True)
def no_delays(monkeypatch):
    monkeypatch.setattr(demo, "DELAY_SCALE", 0.0)


def stub_case(case_id="c1", **stub):
    return {
        "id": case_id,
        "task": "describe_image",
        "image": "images/x.jpg",
        "must_include": ["a crosswalk"],
        "stub": stub,
    }


def good_judge(present=True):
    return {
        "must_include": [{"item": "a crosswalk", "evidence": "", "present": present}],
        "must_not_include": [],
        "reason": "",
        "score": int(present),
    }


def test_committed_demo_file_loads_and_every_case_has_a_stub():
    cases, stubs = demo.load_demo()
    assert cases
    assert set(stubs) == {c.id for c in cases}


def test_demo_showcases_every_outcome_for_both_tasks():
    """The demo exists to show the UX, so it must exercise every branch of the report."""
    cases, stubs = demo.load_demo()
    suite = asyncio.run(run_suite(cases, demo.StubTarget(stubs), demo.StubJudge(stubs)))

    statuses = {(r.case.task, r.status) for r in suite.results}
    for task in Task:
        assert (task, CaseStatus.PASSED) in statuses
        assert (task, CaseStatus.FAILED) in statuses
    assert any(r.verdict and r.verdict.missing for r in suite.results)
    assert any(r.verdict and r.verdict.forbidden_present for r in suite.results)
    assert {r.error_stage for r in suite.results if r.status is CaseStatus.ERROR} == {"target", "judge"}


def test_stub_blocks_are_not_part_of_the_real_dataset_schema():
    with pytest.raises(DatasetError, match="stub"):
        load_dataset(demo.DEMO_DATASET)


def test_load_demo_requires_a_stub_for_every_case(write_json):
    path = write_json({"cases": [{"id": "c1", "task": "read_text", "image": "x.png", "must_include": ["EXIT"]}]})
    with pytest.raises(DatasetError, match="stub"):
        demo.load_demo(path)


@pytest.mark.parametrize(
    "stub, fragment",
    [
        ({}, "exactly one of"),
        ({"response": "x", "target_error": "y", "judge": {}}, "exactly one of"),
        ({"response": "x"}, "judge"),
        ({"target_error": "boom", "judge": {}}, "judge"),
        ({"response": "x", "judge": {}, "latency_s": -1}, "latency_s"),
        ({"response": "x", "judge": {}, "colour": "red"}, "colour"),
    ],
)
def test_load_demo_validates_stub_blocks(write_json, stub, fragment):
    with pytest.raises(DatasetError, match=fragment):
        demo.load_demo(write_json({"cases": [stub_case(**stub)]}))


def test_load_demo_still_validates_the_case_itself(write_json):
    bad = stub_case(response="x", judge=good_judge())
    bad["task"] = "nope"
    with pytest.raises(DatasetError, match="task"):
        demo.load_demo(write_json({"cases": [bad]}))


def test_stub_target_returns_the_canned_response_or_raises(write_json):
    cases, stubs = demo.load_demo(
        write_json({"cases": [stub_case("ok", response="A crosswalk.", judge=good_judge()), stub_case("down", target_error="HTTP 503")]})
    )
    target = demo.StubTarget(stubs, name="stub-model")

    assert isinstance(target, Target)
    assert target.name == "stub-model"
    assert asyncio.run(target.respond(cases[0])) == "A crosswalk."
    with pytest.raises(TargetError, match="HTTP 503"):
        asyncio.run(target.respond(cases[1]))


def test_stub_judge_runs_canned_output_through_the_real_verdict_parser(write_json):
    cases, stubs = demo.load_demo(
        write_json(
            {
                "cases": [
                    stub_case("pass", response="x", judge=good_judge(True)),
                    stub_case("fail", response="x", judge=good_judge(False)),
                    stub_case("garbled", response="x", judge="Score: 1, looks fine"),
                ]
            }
        )
    )
    judge = demo.StubJudge(stubs)

    assert isinstance(judge, Judge)
    assert asyncio.run(judge.judge(cases[0], "x")).score == 1
    assert asyncio.run(judge.judge(cases[1], "x")).missing == ("a crosswalk",)
    with pytest.raises(JudgeError):
        asyncio.run(judge.judge(cases[2], "x"))


def test_stubs_must_match_the_case_they_belong_to():
    _, stubs = demo.load_demo()
    with pytest.raises(KeyError):
        asyncio.run(demo.StubTarget(stubs).respond(make_case("not-in-demo")))
