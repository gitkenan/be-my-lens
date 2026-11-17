"""Terminal reporting with Rich.

Everything that comes from datasets or models is rendered as ``Text`` (never
markup), so brackets in a response cannot break or restyle the output. Rich
degrades to plain text when stdout is not a terminal (CI, pipes) and honours
``NO_COLOR``. Glyphs come from ``terminal.glyphs_for(console)`` (Unicode or
ASCII) and colours from ``theme.palette_for(console)`` (soft palette, readable
on light and dark backgrounds). No colour names are hard-coded here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Sequence

from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .dataset import EvalCase
from .results import CaseResult, CaseStatus, SuiteResult, Summary
from .terminal import UNICODE, Glyphs, glyphs_for
from .theme import SOFT, Palette, palette_for

RESPONSE_PREVIEW_CHARS = 600
DIGEST_MAX_LINES = 2  # per row of the compact Failures & errors section

_LABELS = {CaseStatus.PASSED: "PASS", CaseStatus.FAILED: "FAIL", CaseStatus.ERROR: "ERROR"}
# "target" is the harness's term for the model under test; users see "model".
_STAGE_NAMES = {"target": "model", "judge": "judge"}


def _icon(status: CaseStatus, g: Glyphs) -> str:
    return {CaseStatus.PASSED: g.passed, CaseStatus.FAILED: g.failed, CaseStatus.ERROR: g.error}[status]


def _stage_name(stage: str | None) -> str:
    return _STAGE_NAMES.get(stage or "", stage or "unknown")


def display_path(path: Path | str) -> str:
    """Show paths relative to the working directory when that is shorter."""
    path = Path(path)
    try:
        relative = os.path.relpath(path)
    except ValueError:  # different drive on Windows
        return str(path)
    return relative if len(relative) < len(str(path)) else str(path)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _pct(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.0%}"


# --------------------------------------------------------------------------- header / plan


def render_header(
    console: Console,
    *,
    model: str,
    judge_model: str,
    dataset: str,
    locale: str,
    case_count: int,
    demo: bool = False,
    charset_note: str | None = None,
    started: str | None = None,
) -> None:
    g, p = glyphs_for(console), palette_for(console)
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=p.muted, no_wrap=True)
    grid.add_column()
    grid.add_row("Model under test", Text(g.text(model), style="bold"))
    grid.add_row("Judge", Text(g.text(judge_model), style="bold"))
    grid.add_row("Dataset", Text(g.text(dataset)))
    grid.add_row("Prompt locale", Text(g.text(locale)))
    grid.add_row("Cases", Text(str(case_count)))
    if started:
        grid.add_row("Started", Text(started))
    if demo:
        mode = Text("DEMO", style=f"bold {p.accent}")
        mode.append(f" {g.sep} stubbed model & judge {g.sep} no API calls", style=p.accent)
        grid.add_row("Mode", mode)
    else:
        grid.add_row("Mode", Text(f"live {g.sep} OpenAI Responses API"))
    if charset_note:
        grid.add_row("Output", Text(charset_note, style=p.muted))

    console.print(
        Panel(
            grid,
            title=Text(f"Be My Lens {g.sep} image evals", style="bold"),
            title_align="left",
            box=box.ROUNDED,
            border_style=p.muted,
            expand=False,
        )
    )


def render_plan(console: Console, cases: Sequence[EvalCase]) -> None:
    g, p = glyphs_for(console), palette_for(console)
    table = Table(title="Eval plan (dry run)", box=box.SIMPLE_HEAVY, title_justify="left", border_style=p.muted)
    table.add_column("#", justify="right", style=p.muted)
    table.add_column("Case")
    table.add_column("Task", style=p.accent)
    table.add_column("Image")
    table.add_column("Checks")
    for index, case in enumerate(cases, 1):
        checks = f"{len(case.must_include)} essential"
        if case.must_not_include:
            checks += f" {g.sep} {len(case.must_not_include)} forbidden"
        image_ok = case.image.is_file()
        image = Text(f"{g.passed if image_ok else g.failed} {g.text(display_path(case.image))}", style=p.passed if image_ok else p.failed)
        table.add_row(str(index), Text(g.text(case.id)), case.task.value, image, checks)
    console.print(table)


def render_problems(console: Console, title: str, problems: Iterable[str], hint: str | None = None) -> None:
    g, p = glyphs_for(console), palette_for(console)
    body = Text()
    for i, problem in enumerate(problems):
        if i:
            body.append("\n")
        body.append(f"{g.bullet} ", style=p.failed)
        body.append(g.text(problem))
    if hint:
        body.append("\n\n")
        body.append(g.text(hint), style=p.muted)
    title_text = Text(g.text(title), style=f"bold {p.failed}")
    console.print(Panel(body, title=title_text, title_align="left", border_style=p.failed, expand=False))


# --------------------------------------------------------------------------- live progress


def format_result_line(
    result: CaseResult,
    id_width: int = 0,
    max_width: int | None = None,
    glyphs: Glyphs = UNICODE,
    palette: Palette = SOFT,
) -> Text:
    """One status line per case; truncated with an ellipsis to ``max_width`` so it never wraps.

    The trailing detail is a short label ("1 missing", "model error"). Full messages
    belong in the detail panels, where they have room.
    """
    style = palette.status(result.status)
    line = Text()
    line.append(f"{_icon(result.status, glyphs)} {_LABELS[result.status]:<5}", style=f"bold {style}")
    line.append("  ")
    line.append(f"{result.case.task.value:<14}", style=palette.accent)
    line.append("  ")
    line.append(glyphs.text(result.case.id).ljust(id_width), style="bold")
    line.append(f"  {result.latency_s:5.1f}s", style=palette.muted)

    if result.status is CaseStatus.FAILED and result.verdict:
        parts = []
        if result.verdict.missing:
            parts.append(f"{len(result.verdict.missing)} missing")
        if result.verdict.forbidden_present:
            parts.append(f"{len(result.verdict.forbidden_present)} forbidden")
        line.append("  " + f" {glyphs.sep} ".join(parts), style=style)
    elif result.status is CaseStatus.ERROR:
        line.append(f"  {_stage_name(result.error_stage)} error", style=style)
    if max_width and line.cell_len > max_width:
        line.truncate(max(max_width - len(glyphs.ellipsis), 0))
        line.append(glyphs.ellipsis)
    return line


class LiveProgress:
    """Progress bar plus one line per finished case. The bar is cleared when done."""

    def __init__(self, console: Console, total: int, id_width: int = 0):
        self._console = console
        self._total = total
        self._id_width = id_width
        self._running: list[str] = []
        self._glyphs = glyphs_for(console)
        self._palette = palette_for(console)
        self._progress = Progress(
            SpinnerColumn(self._glyphs.spinner),
            TextColumn("{task.description}", markup=False),  # case ids are user content
            BarColumn(bar_width=24),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        self._task_id = None

    def __enter__(self) -> "LiveProgress":
        self._console.push_theme(self._palette.rich_theme())  # soften Rich's built-in progress colours
        self._progress.start()
        self._task_id = self._progress.add_task(self._description(), total=self._total)
        return self

    def __exit__(self, *exc_info) -> None:
        self._progress.stop()
        self._console.pop_theme()

    def _description(self) -> str:
        if not self._running:
            return "Evaluating"
        extra = f" +{len(self._running) - 1}" if len(self._running) > 1 else ""
        return f"Evaluating {self._running[0]}{extra}"

    def on_start(self, case: EvalCase) -> None:
        self._running.append(self._glyphs.text(case.id))
        self._progress.update(self._task_id, description=self._description())

    def on_result(self, result: CaseResult) -> None:
        shown_id = self._glyphs.text(result.case.id)
        if shown_id in self._running:
            self._running.remove(shown_id)
        console = self._progress.console
        console.print(
            format_result_line(result, self._id_width, max_width=console.width, glyphs=self._glyphs, palette=self._palette)
        )
        self._progress.update(self._task_id, advance=1, description=self._description())


# --------------------------------------------------------------------------- details


def _truncate(text: str, limit: int, ellipsis: str) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " " + ellipsis


def _check_rows(grid: Table, label: str, checks, g: Glyphs, p: Palette, *, forbidden: bool) -> None:
    for i, check in enumerate(checks):
        good = check.present != forbidden
        line = Text()
        line.append(f"{g.passed if good else g.failed} ", style=p.passed if good else f"bold {p.failed}")
        line.append(g.text(check.item), style=None if good else p.failed)
        if check.evidence:
            line.append(f"\n  {g.open_quote}{g.text(check.evidence)}{g.close_quote}", style=f"italic {p.muted}")
        grid.add_row(label if i == 0 else "", line)


def _detail_panel(result: CaseResult, full_response: bool, g: Glyphs, p: Palette) -> Panel:
    style = p.status(result.status)
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=p.muted, no_wrap=True)
    grid.add_column()

    grid.add_row("Image", Text(g.text(display_path(result.case.image))))
    if result.case.notes:
        grid.add_row("Notes", Text(g.text(result.case.notes), style="italic"))

    verdict = result.verdict
    if verdict:
        _check_rows(grid, "Essential", verdict.must_include, g, p, forbidden=False)
        _check_rows(grid, "Forbidden", verdict.must_not_include, g, p, forbidden=True)
        if verdict.reason:
            grid.add_row("Judge", Text(g.text(verdict.reason)))
    if result.error:
        grid.add_row(f"{_stage_name(result.error_stage).capitalize()} error", Text(g.text(result.error), style=style))
    if result.response is not None:
        response = result.response if full_response else _truncate(result.response, RESPONSE_PREVIEW_CHARS, g.ellipsis)
        grid.add_row("Response", Text(g.text(response)))

    title = Text()
    title.append(f"{_icon(result.status, g)} {_LABELS[result.status]}", style=f"bold {style}")
    title.append(f" {g.sep} {result.case.task.value} {g.sep} ", style=p.muted)
    title.append(g.text(result.case.id), style="bold")
    return Panel(grid, title=title, title_align="left", border_style=style, box=box.ROUNDED)


def render_details(
    console: Console, suite: SuiteResult, *, include_passed: bool = False, full_responses: bool = False
) -> None:
    """Full panels: every check with evidence, the judge's reason and the response (used by -v and the report file)."""
    g, p = glyphs_for(console), palette_for(console)
    shown = [r for r in suite.results if include_passed or r.status is not CaseStatus.PASSED]
    if not shown:
        console.print(Text(f"{g.passed} All cases passed.", style=f"bold {p.passed}"))
        return
    console.print()
    title = "All results" if include_passed else "Failures & errors"
    console.print(Rule(Text(title, style="bold"), align="left", style=p.muted))
    for result in shown:
        console.print(_detail_panel(result, full_responses, g, p))


# --------------------------------------------------------------------------- digest

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _fits(console: Console, text: str, width: int, max_lines: int) -> bool:
    return len(Text(text).wrap(console, width)) <= max_lines


def _fit(console: Console, text: str, width: int, max_lines: int, ellipsis: str, suffix: str = "") -> str:
    """Shorten ``text`` (+ ``suffix``) to ``max_lines`` wrapped lines.

    Prefers whole sentences, then whole words with an ellipsis, and only cuts inside
    a word when a single word is longer than the space available.
    """
    text = " ".join(text.split())
    if _fits(console, text + suffix, width, max_lines):
        return text + suffix
    sentences = _SENTENCE_END.split(text)
    for n in range(len(sentences) - 1, 0, -1):
        candidate = " ".join(sentences[:n])
        if _fits(console, candidate + suffix, width, max_lines):
            return candidate + suffix
    words = text.split(" ")
    for n in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:n]).rstrip(",;:") + ellipsis
        if _fits(console, candidate + suffix, width, max_lines):
            return candidate + suffix
    budget = max(width * max_lines - len(ellipsis) - len(suffix), 1)
    return text[:budget] + ellipsis + suffix


def _fit_items(console: Console, items: Sequence[str], width: int, max_lines: int, g: Glyphs) -> str:
    """Join as many items as fit, then summarise the rest as "+N more"."""
    separator = f" {g.sep} "
    for n in range(len(items), 0, -1):
        more = f" +{len(items) - n} more" if n < len(items) else ""
        candidate = separator.join(items[:n]) + more
        if _fits(console, candidate, width, max_lines):
            return candidate
    more = f" +{len(items) - 1} more" if len(items) > 1 else ""
    return _fit(console, items[0], width, max_lines, g.ellipsis, suffix=more)


def _digest_rows(result: CaseResult) -> list[tuple[str, Sequence[str] | str]]:
    """The next level of detail behind a status line: which items, or which error."""
    if result.status is CaseStatus.ERROR:
        return [(f"{_stage_name(result.error_stage)} error", result.error or "unknown error")]
    if result.status is CaseStatus.FAILED and result.verdict:
        rows: list[tuple[str, Sequence[str] | str]] = []
        if result.verdict.missing:
            rows.append(("missing", result.verdict.missing))
        if result.verdict.forbidden_present:
            rows.append(("forbidden", result.verdict.forbidden_present))
        return rows
    return []


def render_digest(console: Console, suite: SuiteResult) -> None:
    """Compact Failures & errors section: one short row per problem, in dataset order.

    Rows are laid out by hand (fixed-width columns, Rich only wraps the detail text)
    so the layout is identical across Rich versions; Rich 14 sizes grid padding
    differently from Rich 15, which squeezed columns in a real terminal.
    """
    g, p = glyphs_for(console), palette_for(console)
    rows = [(result, kind, detail) for result in suite.results for kind, detail in _digest_rows(result)]
    if not rows:
        console.print(Text(f"{g.passed} All cases passed.", style=f"bold {p.passed}"))
        return

    indent, gap = " ", "  "
    id_width = min(max(len(g.text(result.case.id)) for result, _, _ in rows), max(console.width // 3, 8))
    kind_width = max(len(kind) for _, kind, _ in rows)
    detail_width = max(console.width - len(indent) - id_width - len(gap) - kind_width - len(gap), 20)
    continuation = " " * (id_width + len(gap) + kind_width + len(gap))  # follows the indent

    console.print()
    console.print(Rule(Text("Failures & errors", style="bold"), align="left", style=p.muted))
    previous = None
    for result, kind, detail in rows:
        if isinstance(detail, str):
            text = _fit(console, g.text(detail), detail_width, DIGEST_MAX_LINES, g.ellipsis)
        else:
            text = _fit_items(console, [g.text(item) for item in detail], detail_width, DIGEST_MAX_LINES, g)
        case_id = "" if result is previous else g.text(result.case.id)
        if len(case_id) > id_width:
            case_id = case_id[: id_width - len(g.ellipsis)] + g.ellipsis
        previous = result

        for index, line in enumerate(Text(text).wrap(console, detail_width)):
            line.rstrip()
            row = Text(indent)
            if index == 0:
                row.append(case_id.ljust(id_width), style="bold")
                row.append(gap)
                row.append(kind.ljust(kind_width), style=p.status(result.status))
                row.append(gap)
            else:
                row.append(continuation)
            row.append_text(line)
            console.print(row, no_wrap=True, overflow="crop")


# --------------------------------------------------------------------------- full report


def render_full_report(console: Console, suite: SuiteResult, *, include_passed: bool = False) -> None:
    """Everything about a finished run, rendered from the SuiteResult alone (for the report file)."""
    g, p = glyphs_for(console), palette_for(console)
    render_header(
        console,
        model=suite.model,
        judge_model=suite.judge_model,
        dataset=suite.context.get("dataset", "?"),
        locale=suite.context.get("locale", "?"),
        case_count=len(suite.results),
        demo=suite.context.get("mode") == "demo",
        started=suite.started_at.isoformat(timespec="seconds"),
    )
    id_width = max((len(g.text(r.case.id)) for r in suite.results), default=0)
    for result in suite.results:
        console.print(format_result_line(result, id_width, max_width=console.width, glyphs=g, palette=p))
    render_details(console, suite, include_passed=include_passed, full_responses=True)
    render_summary(console, suite)


# --------------------------------------------------------------------------- summary


def _summary_row(table: Table, name: str, s: Summary, p: Palette, **kwargs) -> None:
    table.add_row(
        name,
        str(s.total),
        Text(str(s.passed), style=p.passed if s.passed else p.muted),
        Text(str(s.failed), style=p.failed if s.failed else p.muted),
        Text(str(s.errors), style=p.error if s.errors else p.muted),
        Text(_pct(s.pass_rate), style="bold"),
        **kwargs,
    )


def render_summary(console: Console, suite: SuiteResult) -> None:
    p = palette_for(console)
    table = Table(title="Summary", title_justify="left", box=box.SIMPLE_HEAVY, border_style=p.muted)
    table.add_column("Task")
    for column in ("Cases", "Passed", "Failed", "Errors", "Pass rate"):
        table.add_column(column, justify="right")
    for task, summary in suite.by_task().items():
        _summary_row(table, task.value, summary, p)
    table.add_section()
    total = suite.summary()
    _summary_row(table, "total", total, p, style="bold")
    console.print()
    console.print(table)

    g = glyphs_for(console)
    style = p.passed if suite.exit_code == 0 else (p.failed if total.failed else p.error)
    line = Text()
    line.append(f"{total.passed}/{total.scored} passed ({_pct(total.pass_rate)})", style=f"bold {style}")
    line.append(f" {g.sep} {total.failed} failed", style=p.failed if total.failed else p.muted)
    line.append(f" {g.sep} {_plural(total.errors, 'error')}", style=p.error if total.errors else p.muted)
    line.append(f" {g.sep} {suite.duration_s:.1f}s", style=p.muted)
    console.print(Padding(line, (0, 1)))
    if total.errors:
        console.print(
            Padding(Text("Errors are not scored: the pass rate only counts cases the judge graded.", style=p.muted), (0, 1))
        )
