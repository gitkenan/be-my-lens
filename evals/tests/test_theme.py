"""Colour palette: soft, and readable on both light and dark terminal backgrounds."""

import re

import pytest
from rich.color import Color
from rich.console import Console

from lens_evals.results import CaseStatus
from lens_evals.theme import BASIC, SOFT, palette_for

MIN_CONTRAST = 3.0  # WCAG minimum for UI components / large text


def _luminance(hex_colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = Color.parse(hex_colour).get_truecolor()
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _colours(palette):
    return {name: value for name, value in vars(palette).items() if isinstance(value, str)}


@pytest.mark.parametrize("name, colour", sorted(_colours(SOFT).items()))
def test_soft_palette_is_readable_on_white_and_on_black(name, colour):
    lum = _luminance(colour)
    on_white = 1.05 / (lum + 0.05)
    on_black = (lum + 0.05) / 0.05
    assert on_white >= MIN_CONTRAST, f"{name} {colour} is too light for white backgrounds ({on_white:.1f}:1)"
    assert on_black >= MIN_CONTRAST, f"{name} {colour} is too dark for black backgrounds ({on_black:.1f}:1)"


def test_soft_palette_uses_fixed_xterm_cube_indices_not_theme_dependent_ansi_colours():
    """color(16..255) is emitted verbatim by every Rich version; 0..15 are remapped by terminal themes."""
    for colour in _colours(SOFT).values():
        match = re.fullmatch(r"color\((\d+)\)", colour)
        assert match and 16 <= int(match.group(1)) <= 255, colour


def test_basic_palette_avoids_yellow_and_bright_ansi_colours():
    for colour in _colours(BASIC).values():
        assert "yellow" not in colour and "bright" not in colour


def test_status_colours_are_distinct():
    for palette in (SOFT, BASIC):
        colours = {palette.status(s) for s in CaseStatus}
        assert len(colours) == len(CaseStatus)


@pytest.mark.parametrize(
    "color_system, expected",
    [("truecolor", SOFT), ("256", SOFT), ("standard", BASIC), ("windows", BASIC), (None, SOFT)],
)
def test_palette_follows_the_terminal_colour_support(color_system, expected):
    console = Console(color_system=color_system, force_terminal=True)
    assert palette_for(console) is expected


def test_rich_theme_overrides_riches_loud_builtin_progress_and_rule_colours():
    theme = SOFT.rich_theme()
    for name in ("progress.elapsed", "progress.download", "progress.spinner", "bar.complete", "bar.finished", "bar.pulse", "bar.back", "rule.line"):
        assert name in theme.styles, name
    assert "yellow" not in str(theme.styles["progress.elapsed"])
