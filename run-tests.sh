#!/usr/bin/env bash
# run-tests.sh: one entry point for every Be My Lens test suite.
#
#   ./run-tests.sh                  # run every suite that can run here
#   ./run-tests.sh backend jieshuo  # run selected suites
#   ./run-tests.sh --coverage       # ...and print a combined coverage report
#   ./run-tests.sh doctor           # check what this machine can run, and why
#   ./run-tests.sh --help
#
# Nothing needs to be set up first: the Python virtualenv is created and kept in sync
# with the requirement files automatically, and Gradle is picked automatically (the repo
# wrapper if it is available, otherwise a locally installed Gradle such as /opt/gradle-*).
# See docs/testing.md for what each suite covers.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO" || exit 1

# Settings (each has a command-line option; the BML_* environment variables are handy in CI).
VENV="${BML_VENV:-$REPO/server/.venv}"
PYTHON_OVERRIDE="${BML_PYTHON:-}"
GRADLE_MODE="${BML_GRADLE:-auto}"
COVERAGE=0
OFFLINE=0
FAIL_FAST=0
RECREATE_VENV=0
RESULTS_DIR="$REPO/build/test-results"
COVERAGE_DIR="$REPO/build/coverage"
MIN_PYTHON="3.10"
MIN_JAVA=17
export PYTHONDONTWRITEBYTECODE=1

# Output --------------------------------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD=$'\e[1m' DIM=$'\e[2m' RED=$'\e[31m' GREEN=$'\e[32m' YELLOW=$'\e[33m' BLUE=$'\e[34m' RESET=$'\e[0m'
else
    BOLD="" DIM="" RED="" GREEN="" YELLOW="" BLUE="" RESET=""
fi

say() { printf '%s\n' "$*"; }
info() { printf '%s==>%s %s\n' "$BLUE$BOLD" "$RESET" "$*"; }
warn() { printf '%swarning:%s %s\n' "$YELLOW$BOLD" "$RESET" "$*" >&2; }
error() { printf '%serror:%s %s\n' "$RED$BOLD" "$RESET" "$*" >&2; }
die() { error "$*"; exit 2; }
rel() { printf '%s' "${1#"$REPO"/}"; }

usage() {
    cat <<EOF
${BOLD}Usage:${RESET} ./run-tests.sh [options] [suite...] [-- extra args]

${BOLD}Suites${RESET} (default: all)
  backend       FastAPI backend, server/tests                     needs Python >= $MIN_PYTHON
  jieshuo       Jieshuo Lua plugins, tests/jieshuo                needs Python >= $MIN_PYTHON
  android       Android tests on the JVM harness, tests/android-jvm:
                app/src/test + the Robolectric suite              needs JDK $MIN_JAVA+, Gradle 8.7+
  android-unit  only app/src/test on the harness
  robolectric   only the harness's Robolectric suite
  agp           app/src/test through the real Android build       needs the Android SDK
                (skipped, not failed, when no SDK is installed)
  python        backend + jieshuo
  all           backend, jieshuo, android, agp

${BOLD}Commands${RESET}
  list          describe the suites
  doctor        check this machine: Python, JDK, Gradle, Android SDK, network
  clean         delete test outputs and harness build directories

${BOLD}Options${RESET}
  --coverage         collect coverage and print a combined report (build/coverage/)
  --gradle=MODE      auto (default), wrapper, local, or a path to a gradle executable
                     auto: repo wrapper if already downloaded, else a local Gradle 8.7+
                     (PATH, then the newest /opt/gradle-*), else download the wrapper
  --python=PATH      interpreter for creating the test virtualenv
  --venv=DIR         test virtualenv (default: server/.venv)
  --recreate-venv    delete and recreate the test virtualenv first
  --offline          run Gradle offline (requires its caches to be populated)
  --fail-fast        stop after the first suite that fails
  --no-color         plain output (also honours NO_COLOR)
  -h, --help         show this help

Arguments after ${BOLD}--${RESET} go to pytest or Gradle for each selected suite, e.g.
  ./run-tests.sh backend -- -k followup
  ./run-tests.sh robolectric -- --tests '*TtsSpeakerTest'

JUnit XML for every suite that ran is collected in build/test-results/<suite>/.
Exit status: 0 if every selected suite passed or was skipped, 1 if any failed, 2 on usage errors.
EOF
}

list_suites() {
    cat <<EOF
${BOLD}backend${RESET}       server/tests (pytest). The FastAPI app over HTTP with OpenAI faked at the transport
              layer: endpoints, sessions, prompts, configuration, error handling, the API contract.
${BOLD}jieshuo${RESET}       tests/jieshuo (pytest + Lua 5.3 via lupa). The real .lua plugins run in a fake
              Jieshuo host and are checked against the Android integration contract.
${BOLD}android-unit${RESET}  tests/android-jvm 'test' (Gradle). Every test in app/src/test against an
              AGP-style mockable android.jar, without the Android SDK.
${BOLD}robolectric${RESET}   tests/android-jvm 'robolectricTest' (Gradle + Robolectric). Repository and image
              pipeline, LensViewModel, text-to-speech and Intent delivery on a real framework.
${BOLD}android${RESET}       android-unit + robolectric.
${BOLD}agp${RESET}           ./gradlew :app:testDebugUnitTest. The real Android build; needs the Android SDK.
EOF
}

# Arguments ----------------------------------------------------------------------------

COMMAND="run"
SUITES=()
PASSTHROUGH=()
add_suites() {
    local suite existing
    for suite in "$@"; do
        for existing in ${SUITES[@]+"${SUITES[@]}"}; do [[ "$existing" == "$suite" ]] && continue 2; done
        SUITES+=("$suite")
    done
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help) usage; exit 0 ;;
        --coverage) COVERAGE=1 ;;
        --offline) OFFLINE=1 ;;
        --fail-fast) FAIL_FAST=1 ;;
        --recreate-venv) RECREATE_VENV=1 ;;
        --no-color) BOLD="" DIM="" RED="" GREEN="" YELLOW="" BLUE="" RESET="" ;;
        --gradle=*) GRADLE_MODE="${1#*=}" ;;
        --python=*) PYTHON_OVERRIDE="${1#*=}" ;;
        --venv=*) VENV="${1#*=}" ;;
        --gradle | --python | --venv)
            [[ $# -ge 2 ]] || die "$1 needs a value"
            case "$1" in --gradle) GRADLE_MODE="$2" ;; --python) PYTHON_OVERRIDE="$2" ;; --venv) VENV="$2" ;; esac
            shift ;;
        --) shift; PASSTHROUGH=("$@"); break ;;
        list | doctor | clean) COMMAND="$1" ;;
        all) add_suites backend jieshuo android-unit robolectric agp ;;
        python) add_suites backend jieshuo ;;
        android) add_suites android-unit robolectric ;;
        backend | jieshuo | android-unit | robolectric | agp) add_suites "$1" ;;
        *) die "unknown suite or option: $1 (see ./run-tests.sh --help)" ;;
    esac
    shift
done
[[ "$VENV" = /* ]] || VENV="$REPO/$VENV"
[[ ${#SUITES[@]} -gt 0 ]] || add_suites backend jieshuo android-unit robolectric agp

# Python --------------------------------------------------------------------------------

python_ok() { # python_ok INTERPRETER: true if it runs and is new enough
    "$1" -c "import sys; sys.exit(sys.version_info < tuple(map(int, '$MIN_PYTHON'.split('.'))))" >/dev/null 2>&1
}

find_python() {
    local candidate
    if [[ -n "$PYTHON_OVERRIDE" ]]; then
        python_ok "$PYTHON_OVERRIDE" && { printf '%s' "$PYTHON_OVERRIDE"; return 0; }
        error "--python $PYTHON_OVERRIDE is missing or older than $MIN_PYTHON"
        return 1
    fi
    # The backend's Docker image uses 3.12, so prefer it.
    for candidate in python3.12 python3.13 python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    error "no Python >= $MIN_PYTHON found (use --python=PATH)"
    return 1
}

requirements_fingerprint() {
    cat server/requirements.txt server/requirements-dev.txt tests/jieshuo/requirements.txt | cksum | cut -d' ' -f1
}

VENV_READY=0
ensure_venv() { # creates the virtualenv if needed and keeps its packages in sync
    [[ $VENV_READY -eq 1 ]] && return 0
    local stamp="$VENV/.run-tests-requirements" want python
    want="$(requirements_fingerprint)"
    if [[ $RECREATE_VENV -eq 1 && -d "$VENV" ]]; then
        info "Recreating $(rel "$VENV")"
        rm -rf "$VENV"
        RECREATE_VENV=0
    fi
    if [[ ! -x "$VENV/bin/python" ]]; then
        python="$(find_python)" || return 1
        info "Creating test virtualenv $(rel "$VENV") with $python ($("$python" -V 2>&1))"
        if ! "$python" -m venv "$VENV" >/dev/null 2>&1; then
            rm -rf "$VENV"
            if command -v uv >/dev/null 2>&1; then
                warn "'$python -m venv' failed; using uv instead"
                uv venv --quiet --seed --python "$python" "$VENV" || return 1
            elif command -v virtualenv >/dev/null 2>&1; then
                warn "'$python -m venv' failed; using virtualenv instead"
                virtualenv --quiet -p "$python" "$VENV" || return 1
            else
                error "'$python -m venv' failed and neither uv nor virtualenv is installed."
                error "On Debian/Ubuntu install the venv module: apt install python3-venv"
                return 1
            fi
        fi
    fi
    if [[ "$(cat "$stamp" 2>/dev/null)" != "$want" ]]; then
        info "Installing test dependencies into $(rel "$VENV")"
        "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check \
            -r server/requirements-dev.txt -r tests/jieshuo/requirements.txt || {
            error "pip install failed"
            return 1
        }
        printf '%s' "$want" >"$stamp"
    fi
    VENV_READY=1
}

# Java and Gradle -----------------------------------------------------------------------

java_bin() {
    if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/java" ]]; then printf '%s' "$JAVA_HOME/bin/java"; else command -v java; fi
}

java_major() { # prints the major version of the JDK Gradle will use, or nothing
    local java version
    java="$(java_bin)" || return 1
    version="$("$java" -version 2>&1 | sed -n 's/.*version "\([^"]*\)".*/\1/p' | head -1)"
    [[ "$version" == 1.* ]] && version="${version#1.}"
    printf '%s' "${version%%[.+-]*}"
}

require_java() {
    local major
    major="$(java_major)"
    if [[ -z "$major" ]]; then
        error "no JDK found (install JDK $MIN_JAVA+ or set JAVA_HOME)"
        return 1
    fi
    if [[ "$major" -lt $MIN_JAVA ]]; then
        error "JDK $major found; JDK $MIN_JAVA+ is required (set JAVA_HOME)"
        return 1
    fi
}

WRAPPER_GRADLE="$(sed -n 's/^distributionUrl=.*gradle-\([0-9.]*\)-.*\.zip$/\1/p' gradle/wrapper/gradle-wrapper.properties)"
MIN_GRADLE="${WRAPPER_GRADLE:-8.7}"

version_at_least() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

gradle_version_of() { "$@" --version 2>/dev/null | sed -n 's/^Gradle \([0-9][0-9.]*\).*/\1/p' | head -1; }

wrapper_cached() {
    compgen -G "${GRADLE_USER_HOME:-$HOME/.gradle}/wrapper/dists/gradle-$WRAPPER_GRADLE-bin/*/gradle-$WRAPPER_GRADLE/bin/gradle" >/dev/null
}

local_gradles() { # local Gradle installs, newest /opt first after the one on PATH
    command -v gradle 2>/dev/null
    compgen -G "/opt/gradle*/bin/gradle" | while read -r g; do
        printf '%s %s\n' "$(basename "$(dirname "$(dirname "$g")")" | sed 's/^gradle-//')" "$g"
    done | sort -rV | cut -d' ' -f2-
}

GRADLE_CMD=()
GRADLE_DESC=""
pick_local_gradle() {
    local candidate version
    while read -r candidate; do
        [[ -x "$candidate" ]] || continue
        version="$(gradle_version_of "$candidate")"
        if [[ -n "$version" ]] && version_at_least "$version" "$MIN_GRADLE"; then
            GRADLE_CMD=("$candidate")
            GRADLE_DESC="$candidate (Gradle $version, local install)"
            return 0
        fi
    done < <(local_gradles)
    return 1
}

use_wrapper() {
    # Invoked through sh so a checkout without the executable bit still works.
    GRADLE_CMD=(sh "$REPO/gradlew")
    GRADLE_DESC="./gradlew (Gradle $WRAPPER_GRADLE, repo wrapper$1)"
}

wrapper_downloads() { # can the wrapper fetch its distribution? (first use only)
    info "Downloading Gradle $WRAPPER_GRADLE for the repo wrapper"
    if command -v timeout >/dev/null 2>&1; then
        timeout 600 sh "$REPO/gradlew" --version >/dev/null 2>&1
    else
        sh "$REPO/gradlew" --version >/dev/null 2>&1
    fi
}

resolve_gradle() {
    [[ ${#GRADLE_CMD[@]} -gt 0 ]] && return 0
    require_java || return 1
    local version
    case "$GRADLE_MODE" in
        wrapper) use_wrapper "" ;;
        local)
            pick_local_gradle || { error "no local Gradle $MIN_GRADLE+ on PATH or in /opt/gradle-*"; return 1; } ;;
        auto)
            if wrapper_cached; then
                use_wrapper ""
            elif pick_local_gradle; then
                GRADLE_DESC="$GRADLE_DESC; wrapper's Gradle $WRAPPER_GRADLE not downloaded, so using this"
            elif wrapper_downloads; then
                use_wrapper ", just downloaded"
            else
                error "no usable Gradle: the wrapper could not download Gradle $WRAPPER_GRADLE and no local"
                error "Gradle $MIN_GRADLE+ was found on PATH or in /opt/gradle-*. Use --gradle=PATH."
                return 1
            fi ;;
        *)
            [[ -x "$GRADLE_MODE" ]] || { error "--gradle $GRADLE_MODE is not an executable"; return 1; }
            version="$(gradle_version_of "$GRADLE_MODE")"
            [[ -n "$version" ]] || { error "--gradle $GRADLE_MODE does not report a Gradle version"; return 1; }
            version_at_least "$version" "$MIN_GRADLE" || warn "Gradle $version is older than $MIN_GRADLE"
            GRADLE_CMD=("$GRADLE_MODE")
            GRADLE_DESC="$GRADLE_MODE (Gradle $version, from --gradle)" ;;
    esac
    info "Using $GRADLE_DESC"
}

run_gradle() { # run_gradle ARGS...: the resolved Gradle with the shared flags
    local flags=(--console=plain)
    [[ $OFFLINE -eq 1 ]] && flags+=(--offline)
    "${GRADLE_CMD[@]}" "$@" "${flags[@]}" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}
}

android_sdk() { # prints the Android SDK location, if any
    local dir
    for dir in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" \
        "$(sed -n 's/^sdk\.dir=//p' local.properties 2>/dev/null | sed 's/\\:/:/g; s/\\\\/\\/g')"; do
        [[ -n "$dir" && -d "$dir" ]] && { printf '%s' "$dir"; return 0; }
    done
    return 1
}

# Suites ------------------------------------------------------------------------------
# Each run_<suite> returns 0 (pass), 1 (fail) or 3 (skipped), and may set SUITE_NOTE.

SUITE_NOTE=""

pytest_suite() { # pytest_suite NAME PATH [extra pytest args...]
    local name="$1" path="$2"
    shift 2
    ensure_venv || return 1
    mkdir -p "$RESULTS_DIR/$name"
    "$VENV/bin/python" -m pytest "$path" -q -o cache_dir="$REPO/build/.pytest_cache" \
        --junitxml="$RESULTS_DIR/$name/junit.xml" "$@" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}
}

run_backend() {
    local cov=()
    [[ $COVERAGE -eq 1 ]] && cov=(--cov --cov-report="xml:$COVERAGE_DIR/backend.xml" --cov-report="html:$COVERAGE_DIR/backend-html")
    pytest_suite backend server/tests ${cov[@]+"${cov[@]}"}
}

run_jieshuo() {
    local status
    # Read by tests/jieshuo/lua_coverage.py.
    [[ $COVERAGE -eq 1 ]] && export JIESHUO_LUA_COVERAGE="$COVERAGE_DIR/lua.json"
    pytest_suite jieshuo tests/jieshuo
    status=$?
    unset JIESHUO_LUA_COVERAGE
    return $status
}

harness_suite() { # harness_suite SUITE_NAME GRADLE_TASK
    local name="$1" task="$2" status
    resolve_gradle || return 1
    rm -rf "tests/android-jvm/build/test-results/$task" "tests/android-jvm/build/jacoco/$task.exec"
    # --warn hides Gradle's task-by-task progress but keeps compiler warnings, test failures
    # and the harness's one-line summary per test task.
    if [[ $COVERAGE -eq 1 ]]; then
        run_gradle -p tests/android-jvm "$task" --warn -Pcoverage
    else
        run_gradle -p tests/android-jvm "$task" --warn
    fi
    status=$?
    collect_junit "tests/android-jvm/build/test-results/$task" "$name"
    return $status
}

run_android-unit() { harness_suite android-unit test; }
run_robolectric() { harness_suite robolectric robolectricTest; }

run_agp() {
    local sdk
    if ! sdk="$(android_sdk)"; then
        SUITE_NOTE="no Android SDK (set ANDROID_HOME or sdk.dir in local.properties)"
        return 3
    fi
    resolve_gradle || return 1
    info "Android SDK: $sdk"
    rm -rf app/build/test-results/testDebugUnitTest
    run_gradle :app:testDebugUnitTest
    local status
    status=$?
    collect_junit app/build/test-results/testDebugUnitTest agp
    return $status
}

collect_junit() { # copies Gradle's JUnit XML to build/test-results/<suite>/
    rm -rf "${RESULTS_DIR:?}/$2"
    mkdir -p "$RESULTS_DIR/$2"
    compgen -G "$1/*.xml" >/dev/null && cp "$1"/*.xml "$RESULTS_DIR/$2/"
}

junit_counts() { # prints "tests failures" summed over a suite's JUnit XML
    cat "$RESULTS_DIR/$1"/*.xml 2>/dev/null | grep -o '<testsuite [^>]*>' | awk '
        { t = $0; sub(/.* tests="/, "", t); sub(/".*/, "", t)
          f = 0; if (match($0, / failures="[0-9]+"/)) f += substr($0, RSTART + 11, RLENGTH - 12)
          e = 0; if (match($0, / errors="[0-9]+"/)) e += substr($0, RSTART + 9, RLENGTH - 10)
          tests += t; failed += f + e }
        END { if (NR) print tests, failed }'
}

# Commands ----------------------------------------------------------------------------

cmd_clean() {
    info "Removing test outputs and harness build directories"
    rm -rf "$RESULTS_DIR" "$COVERAGE_DIR" "$REPO/build/.pytest_cache" \
        tests/android-jvm/build tests/android-jvm/.gradle tests/android-jvm/.kotlin
    say "Done. The test virtualenv ($(rel "$VENV")) was kept; use --recreate-venv to rebuild it."
}

check() { # check LABEL STATUS DETAIL
    local mark
    case "$2" in ok) mark="$GREEN ok $RESET" ;; warn) mark="$YELLOW -- $RESET" ;; *) mark="$RED no $RESET" ;; esac
    printf '  [%s] %-22s %s\n' "$mark" "$1" "$3"
}

reachable() { command -v curl >/dev/null 2>&1 && curl -s -o /dev/null -m 8 -I "$1"; }

cmd_doctor() {
    local python major sdk candidate version can_py=0 can_android=0
    say "${BOLD}Python${RESET}"
    if python="$(find_python 2>/dev/null)"; then
        check "interpreter" ok "$python ($("$python" -V 2>&1))"
        can_py=1
    else
        check "interpreter" no "no Python >= $MIN_PYTHON (backend and jieshuo cannot run)"
    fi
    if [[ -x "$VENV/bin/python" ]]; then
        if [[ "$(cat "$VENV/.run-tests-requirements" 2>/dev/null)" == "$(requirements_fingerprint)" ]]; then
            check "test virtualenv" ok "$(rel "$VENV"), dependencies up to date"
        else
            check "test virtualenv" warn "$(rel "$VENV") exists; dependencies will be installed on the next run"
        fi
    else
        check "test virtualenv" warn "$(rel "$VENV") will be created on the next run"
    fi
    if [[ $can_py -eq 1 ]] && ! "$python" -c "import venv, ensurepip" >/dev/null 2>&1; then
        if command -v uv >/dev/null 2>&1 || command -v virtualenv >/dev/null 2>&1; then
            check "venv module" warn "unavailable; uv/virtualenv will be used instead"
        else
            check "venv module" no "unavailable (apt install python3-venv, or install uv)"
        fi
    fi

    say "${BOLD}Java and Gradle${RESET}"
    major="$(java_major)"
    if [[ -n "$major" && "$major" -ge $MIN_JAVA ]]; then
        check "JDK" ok "$(java_bin) (Java $major)"
        can_android=1
    else
        check "JDK" no "${major:+Java $major is too old; }JDK $MIN_JAVA+ needed for android, robolectric and agp"
    fi
    if wrapper_cached; then
        check "repo wrapper" ok "Gradle $WRAPPER_GRADLE already downloaded (auto mode uses it)"
    else
        check "repo wrapper" warn "Gradle $WRAPPER_GRADLE not downloaded yet"
    fi
    local found_local=0
    while read -r candidate; do
        [[ -x "$candidate" ]] || continue
        version="$(gradle_version_of "$candidate")"
        if [[ -n "$version" ]] && version_at_least "$version" "$MIN_GRADLE"; then
            check "local Gradle" ok "$candidate (Gradle $version)"
            found_local=1
        else
            check "local Gradle" warn "$candidate (Gradle ${version:-?}, too old; $MIN_GRADLE+ needed)"
        fi
    done < <(local_gradles)
    [[ $found_local -eq 0 ]] && check "local Gradle" warn "none on PATH or in /opt/gradle-* (the wrapper will download one)"
    if sdk="$(android_sdk)"; then
        check "Android SDK" ok "$sdk (agp suite will run)"
    else
        check "Android SDK" warn "not found: agp suite will be skipped (others don't need it)"
    fi

    say "${BOLD}Network${RESET} ${DIM}(only needed on the first run, to fill caches)${RESET}"
    if command -v curl >/dev/null 2>&1; then
        reachable https://pypi.org/simple/pytest/ && check "PyPI" ok "reachable" || check "PyPI" no "unreachable (Python suites need it once)"
        reachable https://repo.maven.apache.org/maven2/ && check "Maven Central" ok "reachable" || check "Maven Central" no "unreachable (Android harness needs it once)"
        reachable https://dl.google.com/dl/android/maven2/androidx/test/monitor/1.7.2/monitor-1.7.2.pom \
            && check "Google Maven" ok "reachable" || check "Google Maven" no "unreachable (robolectric needs a few AndroidX artifacts once)"
        if ! wrapper_cached; then
            reachable https://services.gradle.org/distributions/ && check "services.gradle.org" ok "reachable (wrapper can download)" \
                || check "services.gradle.org" warn "unreachable: a local Gradle is needed for Android suites"
        fi
    else
        check "network" warn "curl not installed; skipped"
    fi

    say "${BOLD}Suites that can run here${RESET}"
    [[ $can_py -eq 1 ]] && say "  backend, jieshuo"
    [[ $can_android -eq 1 ]] && say "  android-unit, robolectric (if a Gradle is available, see above)"
    android_sdk >/dev/null && [[ $can_android -eq 1 ]] && say "  agp"
    return 0
}

# Run ---------------------------------------------------------------------------------

case "$COMMAND" in
    list) list_suites; exit 0 ;;
    doctor) cmd_doctor; exit 0 ;;
    clean) cmd_clean; exit 0 ;;
esac

if [[ $COVERAGE -eq 1 ]]; then
    # Start clean so no report mixes in data from an earlier run.
    rm -rf "$COVERAGE_DIR" tests/android-jvm/build/jacoco
    mkdir -p "$COVERAGE_DIR"
fi

NAMES=() RESULTS=() DETAILS=() TIMES=()
overall=0
for suite in "${SUITES[@]}"; do
    say ""
    info "${BOLD}$suite${RESET}"
    SUITE_NOTE=""
    rm -rf "${RESULTS_DIR:?}/$suite" # never report results left over from an earlier run
    started=$SECONDS
    "run_$suite"
    status=$?
    elapsed=$((SECONDS - started))
    counts="$(junit_counts "$suite")"
    case $status in
        0) result="${GREEN}PASS${RESET}" ;;
        3) result="${YELLOW}SKIP${RESET}" ;;
        *) result="${RED}FAIL${RESET}"; overall=1 ;;
    esac
    if [[ $status -ne 3 && -n "$counts" ]]; then
        read -r total failed <<<"$counts"
        SUITE_NOTE="$total tests"
        [[ "$failed" != 0 ]] && SUITE_NOTE="$total tests, $failed failed"
    elif [[ $status -ne 0 && $status -ne 3 && -z "$SUITE_NOTE" ]]; then
        SUITE_NOTE="no tests ran; see the errors above"
    fi
    NAMES+=("$suite") RESULTS+=("$result") DETAILS+=("$SUITE_NOTE") TIMES+=("${elapsed}s")
    if [[ $status -ne 0 && $status -ne 3 && $FAIL_FAST -eq 1 ]]; then
        warn "stopping after the first failure (--fail-fast)"
        break
    fi
done

if [[ $COVERAGE -eq 1 ]]; then
    covered_suites=()
    for i in "${!NAMES[@]}"; do
        case "${NAMES[$i]}" in
            backend | jieshuo) covered_suites+=("${NAMES[$i]}") ;;
            android-unit | robolectric) [[ " ${covered_suites[*]-} " == *" android "* ]] || covered_suites+=(android) ;;
        esac
    done
    if [[ " ${covered_suites[*]-} " == *" android "* ]]; then
        say ""
        info "Android coverage report"
        run_gradle -p tests/android-jvm coverageReport -Pcoverage -q >/dev/null || warn "Android coverage report failed"
    fi
    if [[ ${#covered_suites[@]} -gt 0 ]] && ensure_venv; then
        say ""
        suites_csv="$(IFS=,; printf '%s' "${covered_suites[*]}")"
        "$VENV/bin/python" tests/tools/coverage_summary.py --suites "$suites_csv" --markdown "$COVERAGE_DIR/summary.md"
    fi
fi

say ""
say "${BOLD}Summary${RESET}"
for i in "${!NAMES[@]}"; do
    printf '  %-14s %s  %6s   %s\n' "${NAMES[$i]}" "${RESULTS[$i]}" "${TIMES[$i]}" "${DETAILS[$i]}"
done
say "  ${DIM}JUnit XML: $(rel "$RESULTS_DIR")/<suite>/${RESET}"
exit $overall
