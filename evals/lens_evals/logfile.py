"""The full plain-text report written after every run.

The terminal shows a compact digest. The complete detail panels (every check with
evidence, the judge's reasons and untruncated responses) go to a file, by default
``<system temp dir>/lens-evals/`` (``/tmp/lens-evals`` on Linux). The file has no
colour codes, and follows the terminal's charset so ``less``/``cat`` show it
correctly in the same terminal.
"""

from __future__ import annotations

import itertools
import os
import re
import tempfile
from pathlib import Path

from rich.console import Console

from .report import render_full_report
from .results import SuiteResult
from .terminal import AsciiStream

LOG_DIR_NAME = "lens-evals"
REPORT_WIDTH = 100
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def default_log_dir() -> str:
    return os.path.join(tempfile.gettempdir(), LOG_DIR_NAME)


def write_report(
    suite: SuiteResult, log_dir: Path | str, *, include_passed: bool = False, ascii_only: bool = False
) -> Path:
    """Write the full report and return its path. Never overwrites an existing file; raises OSError on failure."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = suite.started_at.strftime("%Y%m%d-%H%M%S")
    mode = suite.context.get("mode", "run")
    model = _UNSAFE_FILENAME_CHARS.sub("_", suite.model).strip("_") or "model"
    base = f"{stamp}-{mode}-{model}"

    for attempt in itertools.count(1):
        path = log_dir / (f"{base}.log" if attempt == 1 else f"{base}-{attempt}.log")
        try:
            handle = open(path, "x", encoding="utf-8")
        except FileExistsError:
            continue
        break

    with handle:
        console = Console(
            file=AsciiStream(handle) if ascii_only else handle,
            width=REPORT_WIDTH,
            force_terminal=False,  # plain text even when FORCE_COLOR is set
            color_system=None,
            highlight=False,
            emoji=False,
        )
        render_full_report(console, suite, include_passed=include_passed)
    return path
