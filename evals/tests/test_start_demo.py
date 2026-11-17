"""start_demo.sh: only the fast, side-effect-free paths (no venv creation, no network)."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "start_demo.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")


def run(*args, env=None):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=30, env={**os.environ, **(env or {})}
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


def test_script_has_valid_bash_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_script_output_is_plain_ascii_so_it_renders_in_any_terminal():
    assert SCRIPT.read_bytes().isascii()


def test_help_describes_the_default_flow_and_options():
    result = run("--help")
    assert result.returncode == 0
    for fragment in ("--tests-only", "--demo-only", "--fresh", "PYTHON", "unit tests", "--demo"):
        assert fragment in result.stdout


@pytest.mark.parametrize("args", [["--bogus"], ["--tests-only", "--demo-only"]])
def test_invalid_options_are_usage_errors(args):
    result = run(*args)
    assert result.returncode == 2
    assert "--help" in result.stderr


def test_missing_interpreter_is_reported_before_anything_is_created(tmp_path):
    result = run(env={"PYTHON": str(tmp_path / "no-such-python")})
    assert result.returncode != 0
    assert "no-such-python" in result.stderr


def test_too_old_python_is_reported(tmp_path):
    fake = tmp_path / "python-old"
    fake.write_text("#!/bin/sh\ncase \"$*\" in *version_info*) exit 1;; *) echo 3.8.10;; esac\n")
    fake.chmod(0o755)
    result = run(env={"PYTHON": str(fake)})
    assert result.returncode != 0
    assert "3.10" in result.stderr and "3.8.10" in result.stderr
