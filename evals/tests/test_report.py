"""Terminal rendering. Uses a recording Rich console; asserts on the plain-text output."""

import re
from datetime import datetime, timezone

import pytest
from fakes import make_case, verdict_for
from rich.console import Console

from lens_evals import report
from lens_evals.dataset import Task
from lens_evals.results import CaseResult, CaseStatus, SuiteResult

CROSSWALK = make_case(
    "crosswalk-red-signal",
    must_include=("a pedestrian crosswalk", "the signal shows a red figure"),
    must_not_include=("says it is safe to cross",),
)
MENU = make_case("cafe-menu", task=Task.READ_TEXT, must_include=("Soup of the day",))


def console():
    return Console(record=True, width=110, force_terminal=False, color_system=None)


def text_of(c):
    return c.export_text()


def suite(results):
    return SuiteResult(
        model="gpt-under-test",
        judge_model="gpt-judge",
        results=results,
        started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        duration_s=12.3,
    )


PASSED = CaseResult(case=MENU, status=CaseStatus.PASSED, response="Soup of the day: lentil", verdict=verdict_for(MENU), latency_s=1.5)
FAILED = CaseResult(
    case=CROSSWALK,
    status=CaseStatus.FAILED,
    response="A zebra crossing. It is safe to cross now.",
    verdict=verdict_for(
        CROSSWALK,
        missing=("the signal shows a red figure",),
        forbidden=("says it is safe to cross",),
        reason="Omits the signal and claims it is safe.",
    ),
    latency_s=2.25,
)
ERRORED = CaseResult(
    case=make_case("receipt", task=Task.READ_TEXT),
    status=CaseStatus.ERROR,
    error="TargetError: OpenAI returned HTTP 429: Rate limit reached",
    error_stage="target",
)


class TestResultLine:
    @pytest.mark.parametrize(
        "result, label",
        [(PASSED, "PASS"), (FAILED, "FAIL"), (ERRORED, "ERROR")],
    )
    def test_shows_status_task_and_case_id(self, result, label):
        c = console()
        c.print(report.format_result_line(result))
        out = text_of(c)
        assert label in out
        assert result.case.id in out
        assert result.case.task.value in out

    def test_failure_line_counts_missing_and_forbidden(self):
        c = console()
        c.print(report.format_result_line(FAILED))
        out = text_of(c)
        assert "1 missing" in out
        assert "1 forbidden" in out
        assert "2.2s" in out or "2.3s" in out

    def test_error_line_names_the_failing_stage(self):
        c = console()
        c.print(report.format_result_line(ERRORED))
        assert "model error" in text_of(c)


def test_header_shows_models_mode_and_case_count():
    c = console()
    report.render_header(
        c, model="gpt-under-test", judge_model="gpt-judge", dataset="datasets/cases.json", locale="ar", case_count=7, demo=True
    )
    out = text_of(c)
    for fragment in ("gpt-under-test", "gpt-judge", "datasets/cases.json", "ar", "7", "DEMO"):
        assert fragment in out


def test_details_explain_each_failure_item_by_item():
    c = console()
    report.render_details(c, suite([PASSED, FAILED, ERRORED]))
    out = text_of(c)

    assert "crosswalk-red-signal" in out
    assert "the signal shows a red figure" in out
    assert "says it is safe to cross" in out
    assert "Omits the signal and claims it is safe." in out
    assert "A zebra crossing. It is safe to cross now." in out
    assert "receipt" in out and "Rate limit reached" in out
    assert "cafe-menu" not in out  # passes are hidden unless verbose


def test_verbose_details_include_passing_cases():
    c = console()
    report.render_details(c, suite([PASSED, FAILED]), include_passed=True)
    out = text_of(c)
    assert "cafe-menu" in out and "Soup of the day: lentil" in out


def test_details_say_so_when_everything_passed():
    c = console()
    report.render_details(c, suite([PASSED]))
    assert "All cases passed" in text_of(c)


def test_long_responses_are_truncated_unless_full_responses_are_requested():
    long_result = CaseResult(
        case=CROSSWALK, status=CaseStatus.FAILED, response="word " * 400, verdict=FAILED.verdict
    )
    short, full = console(), console()
    report.render_details(short, suite([long_result]))
    report.render_details(full, suite([long_result]), full_responses=True)
    assert "…" in text_of(short)
    assert len(text_of(full)) > len(text_of(short))


def test_user_content_is_never_interpreted_as_rich_markup():
    tricky = CaseResult(
        case=make_case("markup", must_include=("[bold]sign[/bold]",)),
        status=CaseStatus.FAILED,
        response="Sign reads [red]DANGER[/] and [/oops]",
        verdict=verdict_for(make_case("markup", must_include=("[bold]sign[/bold]",)), missing=("[bold]sign[/bold]",)),
    )
    c = console()
    report.render_details(c, suite([tricky]))
    out = text_of(c)
    assert "[red]DANGER[/]" in out
    assert "[/oops]" in out
    assert "[bold]sign[/bold]" in out


def test_summary_breaks_down_by_task_and_totals():
    c = console()
    report.render_summary(c, suite([PASSED, FAILED, ERRORED]))
    out = text_of(c)
    assert "describe_image" in out and "read_text" in out
    assert "1/2 passed" in out  # errors are excluded from the scored denominator
    assert "50%" in out
    assert "1 error" in out
    assert "12.3s" in out


def test_summary_handles_a_run_where_nothing_was_scored():
    c = console()
    report.render_summary(c, suite([ERRORED]))
    assert "n/a" in text_of(c)


def test_plan_lists_cases_for_dry_runs():
    c = console()
    report.render_plan(c, [CROSSWALK, MENU])
    out = text_of(c)
    assert "crosswalk-red-signal" in out and "cafe-menu" in out
    assert "2 essential" in out and "1 forbidden" in out


def test_problems_are_listed_under_a_title():
    c = console()
    report.render_problems(c, "Dataset is invalid", ["cases[0]: bad", "cases[1]: worse"])
    out = text_of(c)
    assert "Dataset is invalid" in out and "cases[0]: bad" in out and "cases[1]: worse" in out


def test_live_progress_prints_one_line_per_result():
    c = console()
    with report.LiveProgress(c, total=2) as progress:
        progress.on_start(PASSED.case)
        progress.on_result(PASSED)
        progress.on_start(FAILED.case)
        progress.on_result(FAILED)
    out = text_of(c)
    assert "cafe-menu" in out and "crosswalk-red-signal" in out


def test_demo_banner_is_never_truncated():
    c = console()
    report.render_header(c, model="m", judge_model="j", dataset="d.json", locale="ar", case_count=1, demo=True)
    out = text_of(c)
    assert "stubbed model & judge" in out
    assert "no API calls" in out


def test_live_mode_is_labelled_too():
    c = console()
    report.render_header(c, model="m", judge_model="j", dataset="d.json", locale="ar", case_count=1)
    assert "live" in text_of(c)


def test_result_lines_stay_on_one_line_however_long_the_case_id():
    long_id = CaseResult(case=make_case("very-long-case-id-" * 6), status=CaseStatus.ERROR, error="boom", error_stage="target")
    c = Console(record=True, width=80, force_terminal=False, color_system=None)
    c.print(report.format_result_line(long_id, max_width=c.width))
    lines = text_of(c).rstrip("\n").splitlines()
    assert len(lines) == 1
    assert lines[0].endswith("…")


class TestAsciiOutput:
    """Terminals without a UTF-8 locale get ASCII glyphs and boxes, never mojibake."""

    ARABIC = CaseResult(
        case=make_case("arabic-sign", task=Task.READ_TEXT, must_include=("EXIT",)),
        status=CaseStatus.FAILED,
        response="مخرج طوارئ",
        verdict=verdict_for(make_case("arabic-sign", task=Task.READ_TEXT, must_include=("EXIT",)), missing=("EXIT",)),
    )

    def _ascii_console(self):
        from fakes import Stream

        from lens_evals.terminal import make_console

        target = Stream()
        return make_console(target, environ={}, width=100), target

    def test_every_report_section_is_pure_ascii(self):
        c, target = self._ascii_console()
        everything = suite([PASSED, FAILED, ERRORED, self.ARABIC])
        report.render_header(c, model="m", judge_model="j", dataset="d.json", locale="ar", case_count=4, demo=True)
        with report.LiveProgress(c, total=4, id_width=20) as progress:
            for result in everything.results:
                progress.on_start(result.case)
                progress.on_result(result)
        report.render_details(c, everything, include_passed=True, full_responses=True)
        report.render_digest(c, everything)
        report.render_summary(c, everything)
        report.render_plan(c, [CROSSWALK, MENU])
        report.render_problems(c, "Problems", ["one"], hint="hint")
        report.render_details(c, suite([PASSED]))

        out = target.getvalue()
        assert out.isascii()
        assert "+ PASS" in out and "x FAIL" in out and "! ERROR" in out
        assert "DEMO | stubbed model" in out
        assert "\\u0645" in out  # non-Latin user text is escaped, not garbled

    def test_truncation_uses_an_ascii_ellipsis(self):
        from lens_evals.terminal import ASCII

        line = report.format_result_line(
            CaseResult(case=make_case("x" * 300), status=CaseStatus.ERROR, error="E", error_stage="target"),
            max_width=60,
            glyphs=ASCII,
        )
        assert line.plain.endswith("...") and len(line.plain) == 60

    def test_header_explains_why_ascii_was_chosen(self):
        c, target = self._ascii_console()
        report.render_header(
            c, model="m", judge_model="j", dataset="d", locale="ar", case_count=1, charset_note="ASCII (no UTF-8 locale)"
        )
        assert "ASCII (no UTF-8 locale)" in target.getvalue()


def test_ascii_panels_stay_aligned_when_user_text_needs_escaping():
    from fakes import Stream

    from lens_evals.terminal import make_console

    target = Stream()
    c = make_console(target, environ={}, width=80)
    report.render_details(c, suite([TestAsciiOutput.ARABIC]), include_passed=True, full_responses=True)
    panel_lines = [line for line in target.getvalue().splitlines() if line.startswith(("|", "+"))]
    assert panel_lines
    assert all(len(line) == 80 and line.endswith(("|", "+")) for line in panel_lines), panel_lines


def test_progress_description_does_not_interpret_case_ids_as_markup():
    c = console()
    odd = make_case("[bold]weird[/bold]-id")
    with report.LiveProgress(c, total=1) as progress:
        progress.on_start(odd)
        description = progress._progress.tasks[0].description
        rendered = progress._progress.columns[1].render(progress._progress.tasks[0])
    assert "[bold]weird[/bold]-id" in description
    assert "[bold]weird[/bold]-id" in rendered.plain


class TestColours:
    """Full renders in colour terminals must only use the soft palette, never ANSI yellow/green/cyan."""

    LOUD_SGR = re.compile(r"\x1b\[(?:[0-9;]*;)?(?:3[236]|9[0-7]|38;2;249;38;114)m")

    def _render_everything(self, color_system):
        import io

        buffer = io.StringIO()
        c = Console(file=buffer, force_terminal=True, color_system=color_system, width=100)
        everything = suite([PASSED, FAILED, ERRORED])
        report.render_header(c, model="m", judge_model="j", dataset="d", locale="ar", case_count=3, demo=True, charset_note="n")
        with report.LiveProgress(c, total=3, id_width=20) as progress:
            for result in everything.results:
                progress.on_start(result.case)
                progress.on_result(result)
        report.render_details(c, everything, include_passed=True, full_responses=True)
        report.render_digest(c, everything)
        report.render_summary(c, everything)
        report.render_plan(c, [CROSSWALK, MENU])
        report.render_problems(c, "Problems", ["one"], hint="hint")
        return buffer.getvalue()

    @pytest.mark.parametrize("color_system", ["256", "truecolor"])
    def test_no_loud_ansi_colours(self, color_system):
        out = self._render_everything(color_system)
        assert not self.LOUD_SGR.search(out), self.LOUD_SGR.findall(out)[:5]

    def test_soft_palette_is_what_gets_used(self):
        out = self._render_everything("256")
        for index in (65, 131, 137, 67, 244):  # sage, dusty rose, ochre, steel blue, grey
            assert f"38;5;{index}m" in out, index

    def test_no_faint_attribute_which_some_terminals_cannot_render(self):
        assert "\x1b[2m" not in self._render_everything("256")


class TestErrorLines:
    @pytest.mark.parametrize("stage, label", [("target", "model error"), ("judge", "judge error")])
    def test_status_line_shows_a_short_readable_error_label(self, stage, label):
        result = CaseResult(case=ERRORED.case, status=CaseStatus.ERROR, error="OpenAI returned HTTP 429: slow down " * 5, error_stage=stage)
        line = report.format_result_line(result, id_width=22, max_width=75).plain
        assert line.rstrip().endswith(label)
        assert "HTTP 429" not in line and "..." not in line and "…" not in line

    def test_detail_panel_labels_the_stage_in_plain_words(self):
        c = console()
        judge_error = CaseResult(case=MENU, status=CaseStatus.ERROR, error="score contradicts checks", error_stage="judge", response="x")
        report.render_details(c, suite([ERRORED, judge_error]))
        out = text_of(c)
        assert "Model error" in out and "Judge error" in out
        assert "Error (target)" not in out


class TestHeaderFitsNarrowTerminals:
    def test_demo_header_rows_do_not_wrap_at_75_columns(self):
        from fakes import Stream

        from lens_evals.terminal import make_console

        target = Stream()
        c = make_console(target, environ={}, width=75)
        choice_note = "ASCII (no UTF-8 locale; set LANG=C.UTF-8 for Unicode)"
        report.render_header(c, model="stub-vision-model", judge_model="stub-judge", dataset="demo/demo_cases.json",
                             locale="ar", case_count=9, demo=True, charset_note=choice_note)
        lines = target.getvalue().splitlines()
        assert len(lines) == 9  # top border + 7 rows + bottom border: nothing wrapped


class TestDigest:
    """The compact 'Failures & errors' section: the next level of detail, nothing more."""

    def _digest(self, results, width=100):
        c = Console(record=True, width=width, force_terminal=False, color_system=None)
        report.render_digest(c, suite(results))
        return text_of(c)

    def test_names_the_missing_and_forbidden_items_and_the_error(self):
        out = self._digest([PASSED, FAILED, ERRORED])
        assert "crosswalk-red-signal" in out and "receipt" in out
        assert "missing" in out and "the signal shows a red figure" in out
        assert "forbidden" in out and "says it is safe to cross" in out
        assert "model error" in out and "Rate limit reached" in out
        assert "cafe-menu" not in out  # passing cases are not listed

    def test_does_not_repeat_the_full_detail(self):
        out = self._digest([FAILED])
        assert FAILED.response not in out  # responses live in the full report
        assert "quote" not in out  # evidence too
        assert "Omits the signal" not in out  # and the judge's reasoning
        assert "a pedestrian crosswalk" not in out  # items that were fine are not news

    def test_one_row_per_problem_kind(self):
        lines = [line for line in self._digest([FAILED, ERRORED]).splitlines() if line.strip()]
        assert len(lines) == 1 + 3  # rule + missing row + forbidden row + error row

    def test_uses_at_most_a_fifth_of_the_space_of_the_full_panels(self):
        import asyncio

        from lens_evals import demo
        from lens_evals.runner import run_suite

        original_scale = demo.DELAY_SCALE
        demo.DELAY_SCALE = 0
        try:
            cases, stubs = demo.load_demo()
            demo_suite = asyncio.run(run_suite(cases, demo.StubTarget(stubs), demo.StubJudge(stubs)))
        finally:
            demo.DELAY_SCALE = original_scale
        full, compact = console(), console()
        report.render_details(full, demo_suite)
        report.render_digest(compact, demo_suite)
        full_lines, compact_lines = len(text_of(full).splitlines()), len(text_of(compact).splitlines())
        assert compact_lines <= full_lines * 0.2, (compact_lines, full_lines)

    def test_long_error_messages_are_shortened_at_a_sentence_boundary(self):
        chatty = CaseResult(
            case=make_case("chatty"),
            status=CaseStatus.ERROR,
            error="OpenAI returned HTTP 429: Rate limit reached for requests. Please try again in 20s. " * 4,
            error_stage="target",
        )
        out = self._digest([chatty], width=75)
        assert "Rate limit reached for requests." in " ".join(out.split())
        assert "…" not in out and "..." not in out
        assert len([line for line in out.splitlines() if line.strip()]) <= 3  # rule + at most 2 lines

    def test_unbroken_long_text_gets_an_ellipsis_rather_than_overflowing(self):
        blob = CaseResult(case=make_case("blob"), status=CaseStatus.ERROR, error="x" * 500, error_stage="judge")
        out = self._digest([blob], width=75)
        assert "…" in out
        assert all(len(line) <= 75 for line in out.splitlines())

    def test_long_item_lists_collapse_to_a_count(self):
        many = make_case("many", must_include=tuple(f"essential element number {i}" for i in range(12)))
        result = CaseResult(case=many, status=CaseStatus.FAILED, response="x", verdict=verdict_for(many, missing=many.must_include))
        out = self._digest([result], width=80)
        assert "essential element number 0" in out
        assert "more" in out and "essential element number 11" not in out

    def test_all_passed(self):
        assert "All cases passed" in self._digest([PASSED])

    def test_user_text_is_not_markup(self):
        odd = make_case("odd", must_include=("[red]x[/red]",))
        result = CaseResult(case=odd, status=CaseStatus.FAILED, response="r", verdict=verdict_for(odd, missing=("[red]x[/red]",)))
        assert "[red]x[/red]" in self._digest([result])


def test_full_report_renders_everything_from_the_suite_alone():
    c = Console(record=True, width=100, force_terminal=False, color_system=None)
    s = suite([PASSED, FAILED, ERRORED])
    s.context.update({"dataset": "d.json", "locale": "ar", "mode": "demo"})
    report.render_full_report(c, s, include_passed=False)
    out = text_of(c)
    assert "gpt-under-test" in out and "gpt-judge" in out and "d.json" in out  # header
    assert "crosswalk-red-signal" in out and "receipt" in out  # result lines
    assert "A zebra crossing. It is safe to cross now." in out and "Omits the signal" in out  # full panels
    assert "Summary" in out


def test_digest_columns_never_get_squeezed_in_narrow_terminals():
    """Regression: Rich 14's grid sizing squeezed the kind column to 'model er…' in a real 76-column terminal."""
    import io

    rows = [
        CaseResult(case=make_case("train-departure-board"), status=CaseStatus.ERROR, error="OpenAI returned HTTP 429: x.", error_stage="target"),
        CaseResult(case=make_case("p"), status=CaseStatus.ERROR, error="Judge score 1 contradicts its checks.", error_stage="judge"),
    ]
    for width in (60, 75, 76, 80, 120):
        buffer = io.StringIO()
        c = Console(file=buffer, width=width, force_terminal=True, color_system="256")
        report.render_digest(c, suite(rows))
        plain = re.sub(r"\x1b\[[0-9;]*m", "", buffer.getvalue())
        assert "model error" in plain and "judge error" in plain, (width, plain)
        assert all(len(line) <= width for line in plain.splitlines()), width


def test_digest_caps_absurdly_long_case_ids():
    long_id = CaseResult(case=make_case("x" * 200), status=CaseStatus.ERROR, error="boom", error_stage="target")
    c = Console(record=True, width=80, force_terminal=False, color_system=None)
    report.render_digest(c, suite([long_id]))
    out = text_of(c)
    assert "model error" in out and "boom" in out
    assert all(len(line) <= 80 for line in out.splitlines())


def test_digest_continuation_lines_align_with_the_detail_column():
    chatty = CaseResult(
        case=make_case("chatty"), status=CaseStatus.ERROR, error="word " * 30 + "end.", error_stage="target"
    )
    c = Console(record=True, width=60, force_terminal=False, color_system=None)
    report.render_digest(c, suite([chatty]))
    first, second = [line for line in text_of(c).splitlines() if line.strip()][1:3]
    assert first.index("word") == len(second) - len(second.lstrip())
