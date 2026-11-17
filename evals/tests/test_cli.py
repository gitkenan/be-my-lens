"""End-to-end CLI behaviour. Live runs are exercised against a fake OpenAI (httpx.MockTransport)."""

import json
from pathlib import Path

import httpx
import pytest
from rich.console import Console

from lens_evals import cli, demo
from lens_evals.judge import VERDICT_JSON_SCHEMA

PNG = b"\x89PNG\r\n\x1a\nfake"
ENV = {"EVAL_JUDGE_MODEL": "judge-from-env", "OPENAI_API_KEY": "sk-test"}


@pytest.fixture(autouse=True)
def no_demo_delays(monkeypatch):
    monkeypatch.setattr(demo, "DELAY_SCALE", 0.0)


@pytest.fixture
def out():
    return Console(record=True, width=120, force_terminal=False, color_system=None)


def run_cli(out, argv, environ=None, transport=None):
    code = cli.main(argv, console=out, err_console=out, environ=environ if environ is not None else {}, transport=transport)
    return code, out.export_text()


@pytest.fixture
def dataset(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "crosswalk.png").write_bytes(PNG)
    (tmp_path / "images" / "menu.png").write_bytes(PNG)
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "crosswalk",
                        "task": "describe_image",
                        "image": "images/crosswalk.png",
                        "must_include": ["a crosswalk"],
                        "must_not_include": ["says it is safe to cross"],
                    },
                    {"id": "menu", "task": "read_text", "image": "images/menu.png", "must_include": ["Soup of the day"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


class FakeOpenAI:
    """Plays both roles: the model under test (vision requests) and the judge (json_schema requests)."""

    def __init__(self, responses, verdicts):
        self.responses = responses  # task question -> response text
        self.verdicts = verdicts  # response text -> verdict dict
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        if "text" in body:  # judge
            response_text = body["input"][1]["content"][0]["text"].split("<response>\n")[1].split("\n</response>")[0]
            text = json.dumps(self.verdicts[response_text])
        else:
            text = self.responses[body["input"][1]["content"][0]["text"]]
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]})

    @property
    def target_requests(self):
        return [r for r in self.requests if "text" not in r]

    @property
    def judge_requests(self):
        return [r for r in self.requests if "text" in r]


def verdict(include, exclude=()):
    return {
        "must_include": [{"item": "i", "evidence": "", "present": p} for p in include],
        "must_not_include": [{"item": "i", "evidence": "", "present": p} for p in exclude],
        "reason": "because",
        "score": int(all(include) and not any(exclude)),
    }


def fake_openai(describe_ok=True):
    from lens_evals.dataset import Task
    from lens_evals.prompts import load_task_prompts

    prompts = load_task_prompts("ar")
    return FakeOpenAI(
        responses={
            prompts[Task.DESCRIBE_IMAGE].user_question: "A crosswalk.",
            prompts[Task.READ_TEXT].user_question: "Soup of the day",
        },
        verdicts={
            "A crosswalk.": verdict([describe_ok], [False]),
            "Soup of the day": verdict([True]),
        },
    )


class TestDemo:
    def test_demo_runs_the_stubbed_pipeline_without_credentials(self, out):
        code, text = run_cli(out, ["--demo"])
        cases, _ = demo.load_demo()

        assert code == 1  # the demo intentionally includes failures and errors
        assert "DEMO" in text
        for case in cases:
            assert case.id in text
        assert "Summary" in text

    def test_demo_writes_a_results_file(self, out, tmp_path):
        results = tmp_path / "nested" / "demo.json"
        _, text = run_cli(out, ["--demo", "--output", str(results)])

        data = json.loads(results.read_text(encoding="utf-8"))
        assert data["run"]["mode"] == "demo"
        assert len(data["results"]) == len(demo.load_demo()[0])
        assert str(results) in text

    def test_demo_honours_filters(self, out):
        code, text = run_cli(out, ["--demo", "--task", "read_text"])
        cases, _ = demo.load_demo()
        for case in cases:
            assert (case.id in text) == (case.task.value == "read_text")


class TestLiveRun:
    def test_tested_model_comes_from_the_flag_and_judge_model_from_the_env(self, out, dataset):
        fake = fake_openai()
        code, text = run_cli(out, ["--model", "gpt-under-test", "--dataset", str(dataset)], ENV, httpx.MockTransport(fake))

        assert code == 0
        assert {r["model"] for r in fake.target_requests} == {"gpt-under-test"}
        assert {r["model"] for r in fake.judge_requests} == {"judge-from-env"}
        assert all(r["text"]["format"]["schema"] == VERDICT_JSON_SCHEMA for r in fake.judge_requests)
        assert "2/2 passed" in text

    def test_failures_give_exit_code_1_and_are_explained(self, out, dataset):
        code, text = run_cli(
            out, ["--model", "m", "--dataset", str(dataset)], ENV, httpx.MockTransport(fake_openai(describe_ok=False))
        )
        assert code == 1
        assert "a crosswalk" in text
        assert "1/2 passed" in text

    def test_results_file_records_the_run(self, out, dataset, tmp_path):
        results = tmp_path / "run.json"
        run_cli(
            out,
            ["--model", "gpt-under-test", "--dataset", str(dataset), "--output", str(results), "--locale", "en"],
            ENV,
            httpx.MockTransport(fake_openai()),
        )
        data = json.loads(results.read_text(encoding="utf-8"))
        assert data["run"]["model"] == "gpt-under-test"
        assert data["run"]["judge_model"] == "judge-from-env"
        assert data["run"]["locale"] == "en"
        assert data["run"]["mode"] == "live"
        assert [r["status"] for r in data["results"]] == ["passed", "passed"]

    def test_case_filter(self, out, dataset):
        fake = fake_openai()
        code, _ = run_cli(out, ["--model", "m", "--dataset", str(dataset), "--case", "menu"], ENV, httpx.MockTransport(fake))
        assert code == 0
        assert len(fake.target_requests) == 1


class TestUsageErrors:
    def test_model_flag_is_required_outside_demo_mode(self, out, dataset):
        code, text = run_cli(out, ["--dataset", str(dataset)], ENV)
        assert code == 2
        assert "--model" in text

    def test_missing_judge_env_var_is_explained(self, out, dataset):
        code, text = run_cli(out, ["--model", "m", "--dataset", str(dataset)], {"OPENAI_API_KEY": "sk"})
        assert code == 2
        assert "EVAL_JUDGE_MODEL" in text

    def test_missing_dataset_points_to_the_demo(self, out, tmp_path):
        code, text = run_cli(out, ["--model", "m", "--dataset", str(tmp_path / "nope.json")], ENV)
        assert code == 2
        assert "not found" in text
        assert "--demo" in text

    def test_invalid_dataset_lists_every_problem(self, out, write_json):
        path = write_json({"cases": [{"id": "a", "task": "x", "image": "i.png", "must_include": []}]})
        code, text = run_cli(out, ["--model", "m", "--dataset", str(path)], ENV)
        assert code == 2
        assert "task" in text and "must_include" in text

    def test_missing_images_are_listed_before_any_api_call(self, out, dataset, tmp_path):
        (tmp_path / "images" / "menu.png").unlink()
        fake = fake_openai()
        code, text = run_cli(out, ["--model", "m", "--dataset", str(dataset)], ENV, httpx.MockTransport(fake))
        assert code == 2
        assert "menu.png" in text
        assert fake.requests == []

    def test_unknown_case_id(self, out, dataset):
        code, text = run_cli(out, ["--model", "m", "--dataset", str(dataset), "--case", "typo"], ENV)
        assert code == 2
        assert "typo" in text

    def test_filters_that_select_nothing(self, out, tmp_path, write_json):
        path = write_json({"cases": [{"id": "a", "task": "read_text", "image": "i.png", "must_include": ["x"]}]})
        code, text = run_cli(out, ["--model", "m", "--dataset", str(path), "--task", "describe_image"], ENV)
        assert code == 2
        assert "No cases" in text

    def test_unknown_locale(self, out, dataset):
        code, text = run_cli(out, ["--model", "m", "--dataset", str(dataset), "--locale", "xx"], ENV)
        assert code == 2
        assert "xx" in text


class TestDryRun:
    def test_validates_and_lists_cases_without_credentials_or_api_calls(self, out, dataset):
        fake = fake_openai()
        code, text = run_cli(out, ["--dataset", str(dataset), "--dry-run"], {}, httpx.MockTransport(fake))
        assert code == 0
        assert "crosswalk" in text and "menu" in text
        assert fake.requests == []

    def test_still_reports_missing_images(self, out, dataset, tmp_path):
        (tmp_path / "images" / "crosswalk.png").unlink()
        code, text = run_cli(out, ["--dataset", str(dataset), "--dry-run"], {})
        assert code == 2
        assert "crosswalk.png" in text


class TestTerminalCompatibility:
    """Auto-detected output charset, exercised through real (fake) stdout/stderr streams."""

    def _run(self, argv, environ, encoding="utf-8"):
        from fakes import Stream

        stdout, stderr = Stream(encoding), Stream(encoding)
        code = cli.main(argv, stdout=stdout, stderr=stderr, environ=environ)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_no_utf8_locale_gives_pure_ascii_output(self):
        code, out, _ = self._run(["--demo"], environ={})
        assert code == 1
        assert out.isascii()
        assert "Summary" in out and "+ PASS" in out
        assert "LANG=C.UTF-8" in out  # tells the user how to get the Unicode version

    def test_utf8_locale_gives_unicode_output(self):
        _, out, _ = self._run(["--demo"], environ={"LANG": "en_US.UTF-8"})
        assert "✔ PASS" in out and "╭" in out

    def test_non_utf8_output_encoding_does_not_crash(self):
        code, out, _ = self._run(["--demo"], environ={"LANG": "en_US.UTF-8"}, encoding="ascii")
        assert code == 1
        assert out.isascii() and "Summary" in out

    def test_charset_flag_forces_ascii(self):
        _, out, _ = self._run(["--demo", "--charset", "ascii"], environ={"LANG": "en_US.UTF-8"})
        assert out.isascii()

    def test_charset_env_var_forces_unicode(self):
        _, out, _ = self._run(["--demo"], environ={"EVAL_CHARSET": "unicode"})
        assert "✔ PASS" in out

    def test_usage_errors_on_stderr_are_ascii_too(self):
        code, out, err = self._run(["--dataset", "/nope.json", "--model", "m"], environ={})
        assert code == 2
        assert err.isascii() and "Dataset not found" in err
        assert out == ""

    def test_invalid_charset_env_value_is_a_usage_error(self):
        code, _, err = self._run(["--demo"], environ={"EVAL_CHARSET": "emoji"})
        assert code == 2
        assert "EVAL_CHARSET" in err


def test_paths_with_brackets_are_printed_literally(out, tmp_path):
    results = tmp_path / "[run 1]" / "r.json"
    _, text = run_cli(out, ["--demo", "--case", "park-bench", "--output", str(results)])
    assert str(results) in text


class TestCompactOutputAndFullReport:
    def test_terminal_shows_the_digest_and_points_to_the_full_report(self, out, tmp_path):
        code, text = run_cli(out, ["--demo", "--log-dir", str(tmp_path)])
        assert code == 1
        assert "Failures & errors" in text
        assert "a burner is switched on (visible flame)" in text  # digest: which item was missing
        assert "A kitchen counter with a stainless steel stove" not in text  # no full responses
        reports = list(tmp_path.glob("*.log"))
        assert len(reports) == 1
        assert f"Full report: {reports[0]}" in " ".join(text.split())
        assert "A kitchen counter with a stainless steel stove" in reports[0].read_text(encoding="utf-8")

    def test_default_location_is_the_system_temp_dir(self, out):
        import tempfile

        run_cli(out, ["--demo", "--case", "park-bench"])
        assert len(list((Path(tempfile.gettempdir()) / "lens-evals").glob("*-demo-*.log"))) == 1

    def test_verbose_shows_the_full_panels_in_the_terminal(self, out, tmp_path):
        _, text = run_cli(out, ["--demo", "-v", "--log-dir", str(tmp_path)])
        assert "A kitchen counter with a stainless steel stove" in text
        assert "All results" in text

    def test_an_unwritable_log_dir_only_warns(self, out, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        code, text = run_cli(out, ["--demo", "--case", "park-bench", "--log-dir", str(blocker / "logs")])
        assert code == 1  # same as without the problem: the eval result decides the exit code
        assert "Could not write the full report" in text

    def test_summary_stays_last_and_the_digest_is_short(self, out, tmp_path):
        _, text = run_cli(out, ["--demo", "--log-dir", str(tmp_path)])
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Failures & errors"))
        end = next(i for i, line in enumerate(lines) if line.startswith("Summary"))
        assert end - start <= 15
