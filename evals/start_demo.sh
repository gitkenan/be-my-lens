#!/usr/bin/env bash
# Set up evals/.venv, run the eval harness unit tests, then the stubbed demo.
# Run ./start_demo.sh --help for options. Works from any directory.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./start_demo.sh [--tests-only | --demo-only] [--fresh] [-- DEMO_ARGS...]

Sets up the eval harness and previews it. By default it:
  1. creates (or reuses) the virtual environment evals/.venv
  2. installs requirements-dev.txt (only when the requirements files changed)
  3. runs the unit tests (no network, no API keys)
  4. runs the stubbed demo: python -m lens_evals --demo

Options:
  --tests-only   set up, then run the unit tests only
  --demo-only    set up, then run the demo only
  --fresh        delete and recreate evals/.venv first
  -h, --help     show this help
  -- ARGS        pass the remaining arguments to the demo,
                 e.g. ./start_demo.sh -- --charset ascii --verbose

Environment:
  PYTHON         interpreter used to create the venv (default: python3), e.g. PYTHON=python3.12

The demo exits with code 1 by design (its fake data contains failures); this
script treats that as success. Any other failure is returned as-is.
EOF
}

fail() {
    echo "error: $*" >&2
    exit 1
}

usage_error() {
    echo "error: $*" >&2
    echo "Run ./start_demo.sh --help for usage." >&2
    exit 2
}

step() {
    echo
    echo "==> $*"
}

run_tests=1
run_demo=1
fresh=0
demo_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tests-only) run_demo=0 ;;
        --demo-only) run_tests=0 ;;
        --fresh) fresh=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        --)
            shift
            demo_args=("$@")
            break
            ;;
        *) usage_error "unknown option: $1" ;;
    esac
    shift
done
if [[ $run_tests -eq 0 && $run_demo -eq 0 ]]; then
    usage_error "--tests-only and --demo-only cannot be combined"
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

# --- interpreter -------------------------------------------------------------
python="${PYTHON:-python3}"
if ! command -v "$python" >/dev/null 2>&1; then
    fail "Python interpreter '$python' not found. Install Python 3.10+ or set PYTHON=/path/to/python3."
fi
if ! "$python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    found="$("$python" -c 'import platform; print(platform.python_version())' 2>/dev/null || echo unknown)"
    fail "Python 3.10+ is required, but '$python' is $found. Set PYTHON to a newer interpreter."
fi

# --- virtual environment ------------------------------------------------------
venv=".venv"
venv_python="$venv/bin/python"
[[ -x "$venv/Scripts/python.exe" ]] && venv_python="$venv/Scripts/python.exe" # Git Bash on Windows

if [[ $fresh -eq 1 && -d "$venv" ]]; then
    step "Removing $venv (--fresh)"
    rm -rf "$venv"
fi
if [[ -d "$venv" ]] && ! "$venv_python" -c 'import sys' >/dev/null 2>&1; then
    step "Existing $venv is broken (its interpreter is missing); recreating it"
    rm -rf "$venv"
fi
if [[ ! -d "$venv" ]]; then
    step "Creating virtual environment in evals/$venv ($("$python" --version 2>&1))"
    if ! "$python" -m venv "$venv"; then
        rm -rf "$venv"
        fail "could not create the virtual environment. On Debian/Ubuntu install the venv module first:
       sudo apt install python3-venv"
    fi
    venv_python="$venv/bin/python"
    [[ -x "$venv/Scripts/python.exe" ]] && venv_python="$venv/Scripts/python.exe"
fi

# --- requirements (reinstalled only when the requirements files change) -------
stamp="$venv/.requirements.sha256"
wanted="$("$venv_python" -c '
import hashlib, pathlib
digest = hashlib.sha256()
for name in ("requirements.txt", "requirements-dev.txt"):
    digest.update(pathlib.Path(name).read_bytes())
print(digest.hexdigest())
')"
if [[ ! -f "$stamp" || "$(cat "$stamp")" != "$wanted" ]]; then
    step "Installing requirements-dev.txt"
    "$venv_python" -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt
    echo "$wanted" >"$stamp"
else
    step "Requirements already installed (requirements files unchanged)"
fi

# --- unit tests -----------------------------------------------------------------
if [[ $run_tests -eq 1 ]]; then
    step "Running unit tests"
    if ! "$venv_python" -m pytest -p no:cacheprovider; then
        fail "unit tests failed; not starting the demo."
    fi
fi

# --- demo ---------------------------------------------------------------------
if [[ $run_demo -eq 1 ]]; then
    step "Running the demo (stubbed model & judge, no API calls)"
    echo
    status=0
    "$venv_python" -m lens_evals --demo ${demo_args[@]+"${demo_args[@]}"} || status=$?
    if [[ $status -gt 1 ]]; then
        exit "$status"
    fi
    echo
    if [[ $status -eq 1 ]]; then
        echo "Demo finished. Its failures and errors are intentional (fake data in demo/demo_cases.json)."
    else
        echo "Demo finished."
    fi
fi
