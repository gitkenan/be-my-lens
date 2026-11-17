"""Choose an output charset the terminal can actually display.

Python cannot tell what a terminal renders. When the locale is C/POSIX or unset
(common on fresh VMs, over serial consoles and in CI containers), Python 3.7+
switches itself to UTF-8 (PEP 538/540) and even injects ``LC_CTYPE=C.UTF-8``
into its own environment. Rich then trusts ``sys.stdout.encoding == "utf-8"``
and emits box-drawing characters that a Latin-1 terminal shows as ``â``.

So Unicode is used only when the environment *declares* a UTF-8 locale (or the
user forces it). Otherwise the console writes through ``AsciiStream``. That
stream makes Rich draw ASCII boxes, selects the ASCII glyph set, and escapes
any other non-ASCII text (e.g. Arabic responses) as ``\\uXXXX`` instead of
garbling it. Override with ``--charset`` or ``EVAL_CHARSET``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Mapping, TextIO

from rich.console import Console

CHARSET_ENV = "EVAL_CHARSET"
CHARSETS = ("auto", "unicode", "ascii")
UTF8_HINT = "set LANG=C.UTF-8 for Unicode"

# Python's PEP 538 locale coercion writes exactly this value into its own LC_CTYPE.
_COERCED_LC_CTYPE = "C.UTF-8"


class CharsetError(ValueError):
    pass


@dataclass(frozen=True)
class Glyphs:
    passed: str
    failed: str
    error: str
    sep: str
    bullet: str
    ellipsis: str
    open_quote: str
    close_quote: str
    spinner: str  # Rich spinner name
    ascii_only: bool = False

    def text(self, value: str) -> str:
        """Make user content (responses, ids, paths...) displayable *before* Rich measures it for layout."""
        return value.encode("ascii", "backslashreplace").decode("ascii") if self.ascii_only else value


UNICODE = Glyphs("✔", "✘", "!", "·", "•", "…", "“", "”", "dots")
ASCII = Glyphs("+", "x", "!", "|", "-", "...", '"', '"', "line", ascii_only=True)


@dataclass(frozen=True)
class CharsetChoice:
    unicode: bool
    reason: str
    hint: str | None = None

    @property
    def note(self) -> str | None:
        """Short explanation for the report header when output was downgraded to ASCII."""
        if self.unicode:
            return None
        return f"ASCII ({self.reason}" + (f"; {self.hint}" if self.hint else "") + ")"


def _is_utf8(encoding: str | None) -> bool:
    return (encoding or "").lower().replace("-", "").replace("_", "").startswith("utf")


def _declared_locale(environ: Mapping[str, str]) -> tuple[str, str] | None:
    """The locale variable that governs LC_CTYPE, by POSIX precedence, ignoring Python's own coercion."""
    for name in ("LC_ALL", "LC_CTYPE", "LANG"):
        value = (environ.get(name) or "").strip()
        if not value or (name == "LC_CTYPE" and value == _COERCED_LC_CTYPE):
            continue
        return name, value
    return None


def resolve_charset(
    stream: TextIO,
    environ: Mapping[str, str],
    *,
    requested: str | None = None,
    platform: str = sys.platform,
) -> CharsetChoice:
    """Decide between Unicode and ASCII for ``stream``. ``requested`` (the CLI flag) beats ``EVAL_CHARSET``."""
    if requested is None:
        raw = (environ.get(CHARSET_ENV) or "").strip()
        requested = raw.lower() or "auto"
        if requested not in CHARSETS:
            raise CharsetError(f"{CHARSET_ENV} must be one of {', '.join(CHARSETS)}; got {raw!r}")

    encoding = getattr(stream, "encoding", None)
    if not _is_utf8(encoding):
        return CharsetChoice(False, f"{encoding or 'unknown'} encoding", "set PYTHONIOENCODING=utf-8")
    if requested == "ascii":
        return CharsetChoice(False, "forced by --charset or EVAL_CHARSET")
    if requested == "unicode":
        return CharsetChoice(True, "forced by --charset or EVAL_CHARSET")
    if platform == "win32":  # the console API renders Unicode regardless of locale variables
        return CharsetChoice(True, "Windows console")

    declared = _declared_locale(environ)
    if declared and _is_utf8(declared[1].rpartition(".")[2] or declared[1]):
        return CharsetChoice(True, f"{declared[0]}={declared[1]}")
    if declared:
        return CharsetChoice(False, f"locale {declared[0]}={declared[1]} is not UTF-8", UTF8_HINT)
    return CharsetChoice(False, "no UTF-8 locale", UTF8_HINT)


class AsciiStream:
    """Text stream wrapper that reports ``ascii`` to Rich and escapes every non-ASCII character.

    It does not own the wrapped stream and never closes it.
    """

    encoding = "ascii"

    def __init__(self, stream: TextIO):
        self._stream = stream

    def write(self, text: str) -> int:
        self._stream.write(text.encode("ascii", "backslashreplace").decode("ascii"))
        return len(text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def fileno(self) -> int:
        return self._stream.fileno()


def console_for(stream: TextIO, choice: CharsetChoice, **console_kwargs: Any) -> Console:
    return Console(file=stream if choice.unicode else AsciiStream(stream), **console_kwargs)


def make_console(
    stream: TextIO,
    *,
    environ: Mapping[str, str],
    requested: str | None = None,
    platform: str = sys.platform,
    **console_kwargs: Any,
) -> Console:
    choice = resolve_charset(stream, environ, requested=requested, platform=platform)
    return console_for(stream, choice, **console_kwargs)


def glyphs_for(console: Console) -> Glyphs:
    """Glyphs follow the console's encoding, the same signal Rich uses to pick ASCII boxes."""
    return UNICODE if _is_utf8(console.encoding) else ASCII
