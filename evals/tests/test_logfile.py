"""The full plain-text report written after every run."""

import os
import tempfile
from datetime import datetime, timezone

import pytest
from fakes import make_case, verdict_for

from lens_evals.logfile import default_log_dir, write_report
from lens_evals.results import CaseResult, CaseStatus, SuiteResult

CASE = make_case("crosswalk", must_include=("a crosswalk", "a red signal"))
PASSING = make_case("menu")


def suite(model="gpt-4.1-mini"):
    return SuiteResult(
        model=model,
        judge_model="gpt-judge",
        results=[
            CaseResult(case=PASSING, status=CaseStatus.PASSED, response="passing response", verdict=verdict_for(PASSING)),
            CaseResult(case=CASE, status=CaseStatus.FAILED, response="مرحبا " + "long response " * 100,
                       verdict=verdict_for(CASE, missing=("a red signal",), reason="No signal.")),
        ],
        started_at=datetime(2026, 11, 17, 10, 45, 7, tzinfo=timezone.utc),
        duration_s=1.0,
        context={"dataset": "d.json", "locale": "ar", "mode": "demo"},
    )


def test_default_dir_is_lens_evals_in_the_system_temp_dir():
    assert default_log_dir() == os.path.join(tempfile.gettempdir(), "lens-evals")


def test_writes_a_timestamped_file_named_after_mode_and_model(tmp_path):
    path = write_report(suite("ft:gpt-4o:acme/v2"), tmp_path / "logs")
    assert path.parent == tmp_path / "logs"
    assert path.name == "20261117-104507-demo-ft_gpt-4o_acme_v2.log"


def test_contains_the_full_failure_panels_with_untruncated_responses(tmp_path):
    text = write_report(suite(), tmp_path).read_text(encoding="utf-8")
    assert "Failures & errors" in text and "No signal." in text
    assert text.count("long") == 100  # every word of the response, untruncated
    assert "Summary" in text
    assert "passing response" not in text  # passes only with include_passed


def test_include_passed_adds_every_case(tmp_path):
    text = write_report(suite(), tmp_path, include_passed=True).read_text(encoding="utf-8")
    assert "passing response" in text and "All results" in text


def test_is_plain_text_even_when_colour_is_forced(tmp_path, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("TTY_COMPATIBLE", "1")
    text = write_report(suite(), tmp_path).read_text(encoding="utf-8")
    assert "\x1b[" not in text


def test_follows_the_terminal_charset(tmp_path):
    unicode_text = write_report(suite(), tmp_path / "u").read_text(encoding="utf-8")
    ascii_text = write_report(suite(), tmp_path / "a", ascii_only=True).read_text(encoding="utf-8")
    assert "مرحبا" in unicode_text and "╭" in unicode_text
    assert ascii_text.isascii() and "\\u0645" in ascii_text


def test_never_overwrites_an_existing_report(tmp_path):
    first = write_report(suite(), tmp_path)
    second = write_report(suite(), tmp_path)
    assert first != second and first.exists() and second.exists()
    assert second.name == "20261117-104507-demo-gpt-4.1-mini-2.log"


def test_unwritable_location_raises_oserror(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(OSError):
        write_report(suite(), blocker / "logs")
