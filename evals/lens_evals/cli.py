"""Command-line entry point: ``python -m lens_evals``.

Exit codes: 0 = every case passed, 1 = at least one case failed or errored,
2 = usage / configuration / dataset problem (nothing was evaluated),
130 = interrupted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence, TextIO

import httpx
from rich.console import Console
from rich.text import Text

from . import demo as demo_mode
from . import report
from .config import API_KEY_ENV, JUDGE_MODEL_ENV, ConfigError, load_settings
from .dataset import DatasetError, EvalCase, Task, filter_cases, find_missing_images, load_dataset
from .judge import Judge, LLMJudge
from .logfile import default_log_dir, write_report
from .openai_client import ResponsesClient
from .prompts import DEFAULT_LOCALE, PromptSourceError, load_task_prompts
from .results import SuiteResult
from .runner import run_suite
from .targets import OpenAIVisionTarget, Target
from .terminal import CHARSET_ENV, CHARSETS, CharsetChoice, CharsetError, console_for, glyphs_for, resolve_charset
from .theme import palette_for

EVALS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALS_DIR / "datasets" / "cases.json"
USAGE_ERROR = 2


class UsageProblem(Exception):
    def __init__(self, title: str, problems: Sequence[str], hint: str | None = None):
        self.title, self.problems, self.hint = title, list(problems), hint
        super().__init__(title)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lens_evals",
        description="Evaluate Be My Lens image responses (describe image / read text) with an LLM judge.",
        epilog=f"The judge model is read from ${JUDGE_MODEL_ENV}; the API key from ${API_KEY_ENV}.",
    )
    parser.add_argument("--model", help="model under test, e.g. gpt-4.1-mini (required unless --demo or --dry-run)")
    parser.add_argument("--dataset", type=Path, help=f"dataset JSON (default: {report.display_path(DEFAULT_DATASET)})")
    parser.add_argument("--task", action="append", choices=[t.value for t in Task], help="only run this task (repeatable)")
    parser.add_argument("--case", action="append", metavar="ID", help="only run this case id (repeatable)")
    parser.add_argument("--locale", default=DEFAULT_LOCALE, help=f"server prompt locale (default: {DEFAULT_LOCALE})")
    parser.add_argument("--output", type=Path, metavar="PATH", help="also write machine-readable results JSON here")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show the full detail panels for every case in the terminal too"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        metavar="DIR",
        help="where the full report is written (default: <system temp dir>/lens-evals, e.g. /tmp/lens-evals)",
    )
    parser.add_argument(
        "--charset",
        choices=CHARSETS,
        help=f"terminal glyphs: auto (default; Unicode only if the locale declares UTF-8), unicode or ascii. "
        f"Also settable via ${CHARSET_ENV}.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="preview the UX with stubbed model/judge data (no API calls)")
    mode.add_argument("--dry-run", action="store_true", help="validate the dataset, images and prompts; call nothing")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    console: Console | None = None,
    err_console: Console | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    args = build_parser().parse_args(argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    charset_note = None
    try:
        out_choice = resolve_charset(stdout, environ, requested=args.charset)
        err_choice = resolve_charset(stderr, environ, requested=args.charset)
    except CharsetError as exc:
        safe = CharsetChoice(False, "invalid charset setting")
        report.render_problems(err_console or console_for(stderr, safe), "Invalid configuration", [str(exc)])
        return USAGE_ERROR
    if console is None:
        console = console_for(stdout, out_choice)
        charset_note = out_choice.note
    err_console = err_console or console_for(stderr, err_choice)

    try:
        if args.demo:
            return _run_demo(args, console, charset_note)
        return _run_live(args, console, environ, transport, charset_note)
    except UsageProblem as problem:
        report.render_problems(err_console, problem.title, problem.problems, problem.hint)
        return USAGE_ERROR
    except KeyboardInterrupt:
        err_console.print(Text("\nInterrupted.", style=palette_for(err_console).error))
        return 130


# --------------------------------------------------------------------------- modes


def _run_demo(args: argparse.Namespace, console: Console, charset_note: str | None) -> int:
    dataset_path = args.dataset or demo_mode.DEMO_DATASET
    try:
        cases, stubs = demo_mode.load_demo(dataset_path)
    except DatasetError as exc:
        raise UsageProblem("Demo dataset is invalid", exc.errors) from exc
    cases = _select(cases, args)

    target = demo_mode.StubTarget(stubs, name=args.model or demo_mode.DEMO_MODEL_NAME)
    judge = demo_mode.StubJudge(stubs)
    return _execute(args, console, cases, target, judge, dataset_path, demo=True, charset_note=charset_note)


def _run_live(
    args: argparse.Namespace,
    console: Console,
    environ: Mapping[str, str],
    transport: httpx.AsyncBaseTransport | None,
    charset_note: str | None,
) -> int:
    if not args.model and not args.dry_run:
        raise UsageProblem(
            "No model under test",
            ["--model is required, e.g. --model gpt-4.1-mini"],
            hint="Preview the harness without API calls: python -m lens_evals --demo",
        )

    dataset_path = args.dataset or DEFAULT_DATASET
    try:
        cases = load_dataset(dataset_path)
    except DatasetError as exc:
        hint = None
        if not Path(dataset_path).exists():
            hint = "Create it (see evals/README.md, 'Writing eval cases'), or preview the UX with --demo."
        raise UsageProblem("Dataset is invalid" if hint is None else "Dataset not found", exc.errors, hint) from exc
    cases = _select(cases, args)

    missing = find_missing_images(cases)
    if missing:
        raise UsageProblem(
            f"{len(missing)} image(s) not found",
            [f"{case.id}: {report.display_path(case.image)}" for case in missing],
            hint="Image paths are resolved relative to the dataset file.",
        )

    try:
        prompts = load_task_prompts(args.locale)
    except PromptSourceError as exc:
        raise UsageProblem("Could not load the production prompts", [str(exc)]) from exc

    if args.dry_run:
        report.render_plan(console, cases)
        g = glyphs_for(console)
        console.print(Text(f"{g.passed} {len(cases)} case(s) ready. Nothing was sent to any model.", style=palette_for(console).passed))
        return 0

    try:
        settings = load_settings(environ)
    except ConfigError as exc:
        raise UsageProblem(
            "Missing configuration",
            [f"{name} is not set" for name in exc.missing],
            hint=f"export {JUDGE_MODEL_ENV}=<judge model, e.g. gpt-4.1>  and  export {API_KEY_ENV}=<key>",
        ) from exc

    client = ResponsesClient(api_key=settings.api_key, transport=transport)
    target = OpenAIVisionTarget(client=client, model=args.model, prompts=prompts)
    judge = LLMJudge(client=client, model=settings.judge_model)
    return _execute(
        args, console, cases, target, judge, dataset_path, demo=False, client=client, charset_note=charset_note
    )


# --------------------------------------------------------------------------- shared


def _select(cases: list[EvalCase], args: argparse.Namespace) -> list[EvalCase]:
    try:
        selected = filter_cases(cases, tasks=[Task(t) for t in args.task or []], ids=args.case)
    except DatasetError as exc:
        raise UsageProblem("Invalid case filter", exc.errors) from exc
    if not selected:
        raise UsageProblem("No cases selected", ["No cases match the given --task / --case filters."])
    return selected


def _execute(
    args: argparse.Namespace,
    console: Console,
    cases: list[EvalCase],
    target: Target,
    judge: Judge,
    dataset_path: Path,
    *,
    demo: bool,
    client: ResponsesClient | None = None,
    charset_note: str | None = None,
) -> int:
    dataset_label = report.display_path(dataset_path)
    report.render_header(
        console,
        model=target.name,
        judge_model=judge.name,
        dataset=dataset_label,
        locale=args.locale,
        case_count=len(cases),
        demo=demo,
        charset_note=charset_note,
    )

    id_width = max(len(case.id) for case in cases)
    with report.LiveProgress(console, total=len(cases), id_width=id_width) as progress:

        async def run() -> SuiteResult:
            suite_coro = run_suite(
                cases,
                target,
                judge,
                on_start=progress.on_start,
                on_result=progress.on_result,
                context={"dataset": dataset_label, "locale": args.locale, "mode": "demo" if demo else "live"},
            )
            if client is None:
                return await suite_coro
            async with client:  # open and close the HTTP pool inside this event loop
                return await suite_coro

        suite = asyncio.run(run())

    if args.verbose:
        report.render_details(console, suite, include_passed=True, full_responses=True)
    else:
        report.render_digest(console, suite)
    report.render_summary(console, suite)
    _write_full_report(console, suite, args)
    if args.output:
        _write_results(suite, args.output)
        written = f" Results written to {glyphs_for(console).text(str(args.output))}"
        console.print(Text(written, style=palette_for(console).muted))
    return suite.exit_code


def _write_full_report(console: Console, suite: SuiteResult, args: argparse.Namespace) -> None:
    """Write the full detail report; a failure here is reported but never changes the run's outcome."""
    g, p = glyphs_for(console), palette_for(console)
    try:
        path = write_report(
            suite, args.log_dir or default_log_dir(), include_passed=args.verbose, ascii_only=g.ascii_only
        )
    except OSError as exc:
        console.print(Text(f" Could not write the full report: {g.text(str(exc))}", style=p.error))
        return
    console.print(Text(f" Full report: {g.text(str(path))}", style=p.muted))


def _write_results(suite: SuiteResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suite.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
