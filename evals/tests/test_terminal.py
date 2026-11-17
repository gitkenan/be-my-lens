"""Choosing Unicode vs ASCII output so the report never shows mojibake or crashes on encoding."""

import pytest
from fakes import Stream
from rich.panel import Panel
from rich.table import Table

from lens_evals.terminal import (
    ASCII,
    CHARSET_ENV,
    UNICODE,
    AsciiStream,
    CharsetError,
    glyphs_for,
    make_console,
    resolve_charset,
)


def resolve(environ, encoding="utf-8", requested=None, platform="linux"):
    return resolve_charset(Stream(encoding), environ, requested=requested, platform=platform)


class TestAutoDetection:
    @pytest.mark.parametrize(
        "environ",
        [
            {"LANG": "en_US.UTF-8"},
            {"LANG": "C.UTF-8"},  # official python Docker images, GitHub Actions runners
            {"LANG": "de_DE.utf8"},
            {"LC_ALL": "en_GB.UTF-8", "LANG": "C"},  # LC_ALL wins
            {"LC_CTYPE": "UTF-8"},  # macOS style
        ],
    )
    def test_utf8_locale_enables_unicode(self, environ):
        assert resolve(environ).unicode

    @pytest.mark.parametrize(
        "environ",
        [
            {},  # bare VM shell / CI container: nothing declared
            {"LANG": "C"},
            {"LANG": "POSIX"},
            {"LANG": "en_US.ISO-8859-1"},
            {"LC_ALL": "C", "LANG": "en_US.UTF-8"},  # LC_ALL wins
            # Python coerces a C locale by injecting LC_CTYPE=C.UTF-8 into its own environment (PEP 538);
            # that says nothing about the terminal, so it must not count as a UTF-8 declaration.
            {"LC_CTYPE": "C.UTF-8"},
            {"LC_CTYPE": "C.UTF-8", "LANG": "C"},
        ],
    )
    def test_undeclared_or_non_utf8_locale_falls_back_to_ascii(self, environ):
        choice = resolve(environ)
        assert not choice.unicode
        assert "locale" in choice.reason

    def test_coerced_lc_ctype_does_not_hide_a_real_utf8_lang(self):
        assert resolve({"LC_CTYPE": "C.UTF-8", "LANG": "en_US.UTF-8"}).unicode

    @pytest.mark.parametrize("encoding", ["ascii", "cp1252", "latin-1", "ANSI_X3.4-1968"])
    def test_non_utf8_output_encoding_forces_ascii_even_with_a_utf8_locale(self, encoding):
        choice = resolve({"LANG": "en_US.UTF-8"}, encoding=encoding)
        assert not choice.unicode
        assert "encoding" in choice.reason

    def test_windows_trusts_the_output_encoding(self):
        assert resolve({}, platform="win32").unicode
        assert not resolve({}, encoding="cp1252", platform="win32").unicode


class TestOverrides:
    def test_ascii_can_be_forced(self):
        assert not resolve({"LANG": "en_US.UTF-8"}, requested="ascii").unicode

    def test_unicode_can_be_forced_when_the_locale_is_undeclared(self):
        assert resolve({}, requested="unicode").unicode

    def test_forcing_unicode_cannot_bypass_a_non_utf8_output_encoding(self):
        assert not resolve({}, encoding="ascii", requested="unicode").unicode

    def test_env_var_is_used_when_no_flag_is_given(self):
        assert CHARSET_ENV == "EVAL_CHARSET"
        assert not resolve({"LANG": "en_US.UTF-8", "EVAL_CHARSET": "ascii"}).unicode
        assert resolve({"EVAL_CHARSET": " Unicode "}).unicode

    def test_flag_beats_env_var(self):
        assert resolve({"EVAL_CHARSET": "ascii"}, requested="unicode").unicode

    def test_invalid_env_value_is_an_error(self):
        with pytest.raises(CharsetError, match="EVAL_CHARSET"):
            resolve({"EVAL_CHARSET": "emoji"})

    def test_auto_is_explicitly_allowed(self):
        assert resolve({"LANG": "en_US.UTF-8", "EVAL_CHARSET": "auto"}).unicode


class TestAsciiStream:
    def test_reports_ascii_and_escapes_anything_else(self):
        target = Stream()
        stream = AsciiStream(target)
        stream.write("ok ✔ مرحبا")
        assert stream.encoding == "ascii"
        assert target.getvalue() == "ok \\u2714 \\u0645\\u0631\\u062d\\u0628\\u0627"

    def test_delegates_tty_and_flush(self):
        assert AsciiStream(Stream(tty=True)).isatty()
        assert not AsciiStream(Stream(tty=False)).isatty()
        AsciiStream(Stream()).flush()

    def test_never_closes_the_wrapped_stream(self):
        target = Stream()
        stream = AsciiStream(target)
        del stream
        assert not target.closed


class TestMakeConsole:
    def test_ascii_console_emits_only_ascii_for_rich_widgets_and_user_text(self):
        target = Stream()
        console = make_console(target, environ={}, width=60)
        table = Table(title="t")
        table.add_column("col")
        table.add_row("مرحبا “quoted” …")
        console.print(Panel("box ─ ✔"), table)
        assert target.getvalue().isascii()
        assert glyphs_for(console) is ASCII

    def test_unicode_console_writes_straight_through(self):
        target = Stream()
        console = make_console(target, environ={"LANG": "en_US.UTF-8"}, width=60)
        console.print(Panel("✔ مرحبا"))
        assert "✔ مرحبا" in target.getvalue()
        assert glyphs_for(console) is UNICODE


def test_glyph_sets_are_consistent():
    assert all(v.isascii() for v in ASCII.__dict__.values() if isinstance(v, str))
    assert set(ASCII.__dict__) == set(UNICODE.__dict__)


def test_glyphs_make_user_text_displayable():
    assert ASCII.text("مرحبا ok") == "\\u0645\\u0631\\u062d\\u0628\\u0627 ok"
    assert UNICODE.text("مرحبا ok") == "مرحبا ok"


@pytest.mark.parametrize(
    "environ, encoding, requested, fragment",
    [
        ({}, "utf-8", None, "LANG=C.UTF-8"),
        ({}, "ascii", None, "PYTHONIOENCODING=utf-8"),
        ({"LANG": "en_US.UTF-8"}, "utf-8", "ascii", "--charset"),
    ],
)
def test_ascii_note_is_short_enough_for_one_header_row(environ, encoding, requested, fragment):
    note = resolve(environ, encoding=encoding, requested=requested).note
    assert fragment in note
    assert len(note) <= 56
