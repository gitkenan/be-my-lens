"""Colour palette for the terminal report.

Colours are chosen to be soft and readable on both light and dark terminal
themes. Each has a WCAG contrast of at least 3:1 against pure white *and*
pure black (enforced by ``tests/test_theme.py``). Standard ANSI yellow/green are
about 1.7:1 and 2.2:1 on white, which is why they look harsh on light themes.

* 256-colour and truecolor terminals (nearly all modern ones) get fixed colours
  from the xterm-256 colour cube (indices 16-255), which themes don't remap.
  They are written as ``color(N)`` rather than hex: every Rich version emits the
  index exactly, whereas Rich 13 converts hex to lighter neighbours that fail the
  contrast requirement on white.
* 16-colour terminals get the terminal theme's own ANSI colours (themes tune
  these to their background), avoiding yellow and the bright variants.

Rich's own built-in styles (yellow elapsed time, pink progress bar, bright green
rules) are overridden by ``Palette.rich_theme()``.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.theme import Theme

from .results import CaseStatus


@dataclass(frozen=True)
class Palette:
    passed: str
    failed: str
    error: str
    accent: str  # task names, spinner, progress bar, demo banner
    muted: str  # labels, timings, evidence, borders of neutral panels

    def status(self, status: CaseStatus) -> str:
        return {CaseStatus.PASSED: self.passed, CaseStatus.FAILED: self.failed, CaseStatus.ERROR: self.error}[status]

    def rich_theme(self) -> Theme:
        return Theme(
            {
                "progress.elapsed": self.muted,
                "progress.download": self.muted,
                "progress.percentage": self.muted,
                "progress.spinner": self.accent,
                "bar.back": self.muted,
                "bar.complete": self.accent,
                "bar.finished": self.passed,
                "bar.pulse": self.accent,
                "rule.line": self.muted,
            }
        )


SOFT = Palette(
    passed="color(65)",  # sage        #5f875f  4.1:1 on white, 5.1:1 on black
    failed="color(131)",  # dusty rose  #af5f5f  4.5:1 / 4.6:1
    error="color(137)",  # ochre       #af875f  3.3:1 / 6.5:1
    accent="color(67)",  # steel blue  #5f87af  3.8:1 / 5.6:1
    muted="color(244)",  # mid grey    #808080  3.9:1 / 5.3:1
)

BASIC = Palette(passed="green", failed="red", error="magenta", accent="blue", muted="default")


def palette_for(console: Console) -> Palette:
    return BASIC if console.color_system in ("standard", "windows") else SOFT
