# Be My Lens: response-quality evals

An LLM-as-a-judge harness for the two main image features of the backend:

| Eval task        | Backend endpoint | Production prompt                         |
| ---------------- | ---------------- | ----------------------------------------- |
| `describe_image` | `POST /describe` | `server/prompts/<locale>/describe_image.txt` |
| `read_text`      | `POST /read`     | `server/prompts/<locale>/read_contents.txt`  |

For each image, an author lists the **essential** things a good answer must contain and, optionally, the
**forbidden** things it must not say. The model under test answers with the production prompts, and a judge
LLM scores the answer **1** (every essential item is present and no forbidden item is) or **0** (anything else).

This folder is self-contained. It does not modify or import the backend or the Android app, and it has its
own dependencies and tests.

- [Quick start (demo)](#quick-start-demo)
- [How it works](#how-it-works)
- [Running real evals](#running-real-evals)
- [Writing eval cases](#writing-eval-cases)
- [How the judge decides](#how-the-judge-decides)
- [Output: terminal and results file](#output-terminal-and-results-file)
- [Terminal compatibility (Unicode vs ASCII)](#terminal-compatibility-unicode-vs-ascii)
- [Running in CI](#running-in-ci)
- [Unit tests](#unit-tests)
- [Code map and extension points](#code-map-and-extension-points)
- [Limitations](#limitations)

---

## Quick start (demo)

Requires Python 3.10+.

```bash
evals/start_demo.sh          # creates evals/.venv, installs requirements, runs the unit tests, then the demo
```

The script works from any directory and only reinstalls when the requirements files change, so re-runs are
fast. `--tests-only` and `--demo-only` run one half, `--fresh` rebuilds the venv, and arguments after `--` go
to the demo (e.g. `evals/start_demo.sh -- --charset ascii`). Set `PYTHON=python3.12` to pick the interpreter.
See `--help`.

Or do it by hand:

```bash
cd evals
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # httpx + rich (+ pytest)

python -m lens_evals --demo                # no API key, no images, no network
```

`--demo` runs the whole pipeline (image → response → judge → result) on **fake, committed data** in
[`demo/demo_cases.json`](demo/demo_cases.json). Each demo case carries a canned model response (or a
simulated API failure) and a canned raw judge output. The canned judge output goes through the same verdict
validation as real judge output. The demo deliberately includes passes, failures (a missing safety detail, a
hallucinated dosage, a misread digit, a translated sign) and both kinds of error. It therefore exits with
code `1`, as a real run with failures would.

## How it works

```
dataset.json ──► EvalCase ──► Target (model under test) ──► response ──► Judge (LLM) ──► Verdict 1/0
                     │              uses the production                    checks every        │
                     │              prompts from server/                   item + evidence     ▼
                     └──────────────────────────────────────────────────────────────────► report + JSON
```

- **Faithful to production.** The target sends the same Responses API payload as `server/app.py`: the same
  developer prompt, the same (Arabic) user question and a `detail: "high"` image. Only the model differs.
  Prompt files are read from `server/prompts/`. The user-question constants are extracted from `app.py` with
  `ast`, without importing it. If the backend renames or removes them, `tests/test_prompts.py` fails.
- **Model under test = CLI flag** (`--model`). **Judge model = env var** (`EVAL_JUDGE_MODEL`), so the judge
  stays fixed while you compare models.
- Cases run concurrently (up to 4 at a time, to stay clear of API rate limits). One failing case never
  aborts the run.

## Running real evals

```bash
export OPENAI_API_KEY=sk-...
export EVAL_JUDGE_MODEL=gpt-4.1          # the judge; pick a strong model and keep it fixed

python -m lens_evals --model gpt-4.1-mini                      # uses datasets/cases.json
python -m lens_evals --model gpt-4.1-mini --dataset path/to/cases.json
```

To reuse the backend's key: `set -a; source ../server/.env; set +a`.

| Flag | Purpose |
| --- | --- |
| `--model NAME` | Model under test (required unless `--demo` / `--dry-run`). |
| `--dataset PATH` | Dataset JSON. Default `evals/datasets/cases.json`. |
| `--task {describe_image,read_text}` | Only run one task (repeatable). |
| `--case ID` | Only run specific cases (repeatable). Unknown ids are an error. |
| `--locale ar\|en` | Which `server/prompts/<locale>` to use. Default `ar`, as in production. |
| `--output PATH` | Also write machine-readable results JSON. |
| `-v, --verbose` | Also show the full detail panels for every case in the terminal (the report file always has them). |
| `--log-dir DIR` | Where the full report is written. Default `<system temp dir>/lens-evals`, i.e. `/tmp/lens-evals` on Linux. |
| `--charset auto\|unicode\|ascii` | Terminal glyphs (default `auto`; also `EVAL_CHARSET`). See [terminal compatibility](#terminal-compatibility-unicode-vs-ascii). |
| `--dry-run` | Validate the dataset, images and prompts, and list the plan. Calls nothing and needs no key. |
| `--demo` | Stubbed pipeline on the fake data (see above). |

**Exit codes:** `0` every case passed · `1` at least one case failed or errored · `2` usage, config or
dataset problem (nothing was sent) · `130` interrupted.

Problems are caught before any API call. Invalid datasets list *every* problem at once, missing images
are listed by case, and missing env vars are named.

## Writing eval cases

Put images under `datasets/images/` and describe them in `datasets/cases.json`:

```json
{
  "description": "optional free text",
  "cases": [
    {
      "id": "crosswalk-red-signal",
      "task": "describe_image",
      "image": "images/crosswalk.jpg",
      "must_include": [
        "a pedestrian crosswalk",
        "the pedestrian signal shows a red standing figure"
      ],
      "must_not_include": ["says or implies it is safe to cross now"],
      "notes": "optional; shown in failure reports"
    },
    {
      "id": "cafe-menu",
      "task": "read_text",
      "image": "images/menu.jpg",
      "must_include": ["Soup of the day", "Lentil & lemon £4.50"],
      "must_not_include": ["Espresso"]
    }
  ]
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | yes | Unique. Used by `--case` and in reports. |
| `task` | yes | `describe_image` or `read_text`. |
| `image` | yes | Relative to the dataset file, or absolute. Any common image format; unknown extensions are sent as JPEG, as the backend does. |
| `must_include` | yes | At least one essential element. |
| `must_not_include` | no | Forbidden elements. |
| `notes` | no | Free text for humans. |

Unknown keys are rejected, so a typo like `must_inlcude` can't silently drop expectations. Run
`--dry-run` after editing.

Tips for good checklists:

- **One fact per item.** Put the detail that matters in the item: "the signal shows a *red* figure", not
  "a signal". The judge requires every detail stated in an item.
- **Write criteria in any language.** Responses are usually Arabic; the judge compares meaning for
  `describe_image`.
- **For `read_text`, write the text exactly as printed.** It must appear transcribed in its original language
  and script. Letter case and line breaks may differ; wrong digits, paraphrases and translations fail.
- **Phrase forbidden items as claims** ("states a dosage", "says it is safe to cross") rather than bare
  nouns. Explicitly denying something does not count as saying it.
- Use forbidden items for **hallucinations that matter to a blind user**: invented text, dosages, prices,
  or safety reassurances.

## How the judge decides

The judge prompt and output schema are in [`lens_evals/judge.py`](lens_evals/judge.py).

- The judge sees the checklist and the response, **not the image**. The checklist is the ground truth.
- It must answer in a strict JSON schema (OpenAI structured outputs). For each item it gives a quoted
  `evidence` and a `present` flag, then a one-sentence `reason`, then `score`. The score comes last, so the
  judge checks items before it commits.
- The harness validates the verdict. The score must be `0`/`1`, there must be one check per item, and the
  score must agree with the judge's own checks. A self-contradictory or malformed verdict is reported as a
  **judge error**, never silently counted as a pass or a fail.
- The response is fenced as data, and the judge is told to ignore instructions inside it (defence against
  prompt injection from text in images).
- Rules differ per task: `describe_image` accepts any wording or language with the same meaning;
  `read_text` requires faithful transcription (see the tips above).

## Output: terminal and results file

A run prints, in order:

1. A header: model under test, judge, dataset, locale, case count, and mode.
2. A live progress bar that shows which cases are in flight. Each finished case prints one short line,
   e.g. `✘ FAIL  read_text  train-departure-board  1.8s  1 missing`, or `model error` / `judge error`
   when a call failed.
3. **Failures & errors**: a compact digest with one row per problem. It shows only the next level of
   detail behind each status line: *which* essential items were missing or forbidden items present, or
   *what* the error was. Long text is shortened at a sentence or word boundary (at most two lines per
   row), and long item lists end with `+N more`.
4. A summary table per task, a totals line, and the path of the full report.

```
Failures & errors ───────────────────────────────────────────────────────
 kitchen-stove-on       missing      a burner is switched on (visible flame)
 park-bench             model error  OpenAI returned HTTP 429: Rate limit
                                     reached for requests.
 emergency-exit-sign    missing      EMERGENCY EXIT · Keep clear
```

**Full report.** Every run writes a plain-text report to `/tmp/lens-evals/<time>-<mode>-<model>.log`
(`--log-dir` changes the location, and files are never overwritten). It contains the header, every result
line, and a full panel for each failure and error: every essential and forbidden item with ✔/✘, the judge's
quoted evidence and reason, and the untruncated response. With `-v` it also includes passing cases, and the
same panels are shown in the terminal. The file has no colour codes and follows the terminal's
Unicode/ASCII choice, so `less` displays it correctly. If it cannot be written, the run prints a warning
and its result is unaffected.

**Pass rate = passed ÷ scored cases.** Errors (API failure, bad judge output) are counted and shown
separately, and they still make the exit code `1`. In non-interactive output (CI, pipes) the progress bar
and colours are dropped automatically; set `NO_COLOR=1` to disable colour anywhere. See
[terminal compatibility](#terminal-compatibility-unicode-vs-ascii) for how glyphs are chosen.

`--output results.json` writes a self-describing file (`schema_version`, run metadata including the model and
judge, summary per task, and every result with its response, checks, evidence and errors). Keep these files
to compare models or prompt changes over time. `runs/` and `*.results.json` are git-ignored in this folder.

### Colours

The palette is soft and works on light and dark terminal themes: sage for passes, dusty rose for failures,
ochre for errors, steel blue for accents and mid-grey for secondary text. Every colour has at least 3:1
contrast against both white and black (`tests/test_theme.py` enforces this). Standard ANSI yellow and green
are only about 1.7:1 and 2.2:1 on white. The colours are fixed RGB values, so they look the same in every
256-colour or truecolor terminal. 16-colour terminals fall back to the theme's own ANSI colours, avoiding
yellow. `NO_COLOR=1` turns colour off. Edit the palette in `lens_evals/theme.py`.

## Terminal compatibility (Unicode vs ASCII)

By default the report uses Unicode boxes and glyphs (`╭─╮ ✔ ✘ ·`), but **only when the environment
declares a UTF-8 locale** (`LC_ALL`, `LC_CTYPE` or `LANG`, e.g. `en_US.UTF-8` or `C.UTF-8`). Otherwise it
switches to an all-ASCII rendering (`+-+ + x |`) and the header's **Output** row says why.

Why: when the locale is `C`/`POSIX`/unset (common on fresh VMs, serial consoles and CI containers), Python
switches itself to UTF-8 (PEP 538/540) and reports `utf-8` whatever the terminal can display. Trusting that
makes a Latin-1 terminal show box-drawing characters as `â` and Arabic as `Ø`/`Ù`. A declared locale is the
only reliable signal, so the harness requires one.

- In ASCII mode, non-ASCII text from responses or datasets (e.g. Arabic) is shown as `\uXXXX` escapes,
  so it is lossless and never garbled. The `--output` JSON always contains the original text.
- If Python's output encoding itself is not UTF-8 (`PYTHONIOENCODING=ascii`, some Windows CI logs), ASCII
  is used regardless, so the run never crashes with `UnicodeEncodeError`.
- On Windows the console renders Unicode regardless of locale variables, so the output encoding is trusted.

Overrides:

```bash
export LANG=C.UTF-8                      # recommended: declare that your terminal is UTF-8
python -m lens_evals --charset unicode   # or force Unicode for a single run
python -m lens_evals --charset ascii     # force ASCII (e.g. a terminal that misreports its locale)
export EVAL_CHARSET=ascii                # same as the flag, for CI; the flag wins if both are set
```

## Running in CI

After `pip install -r evals/requirements.txt` (add `-dev` for the tests), the harness needs no other setup:
no terminal configuration, no extra tools. Piped output is detected automatically: no progress-bar
animation and no colour codes, and ASCII when the runner declares no UTF-8 locale.

```bash
pip install -r evals/requirements-dev.txt
cd evals
python -m pytest                                                   # unit tests: no network, no keys
python -m lens_evals --dry-run                                     # validate the dataset & images
python -m lens_evals --model gpt-4.1-mini --output results.json    # live eval (needs the two secrets)
```

- Provide `OPENAI_API_KEY` and `EVAL_JUDGE_MODEL` as CI secrets/variables. Keep `results.json` and the
  full report (`--log-dir reports/`) as build artefacts.
- Gate on the exit code: `0` all passed, `1` failures or errors, `2` misconfiguration.
- `--demo` always exits `1` by design, because its fake data includes failures. Use it to preview the
  output, not as a CI gate.

## Unit tests

```bash
cd evals && python -m pytest          # or, from the repo root: python -m pytest evals
```

The suite was written test-first alongside the harness. It **never calls an LLM**: HTTP goes through
`httpx.MockTransport`, and `tests/conftest.py` blocks real socket connections as a safety net.

| File | Covers |
| --- | --- |
| `test_dataset.py` | Schema validation, all errors reported at once, path resolution, filters. |
| `test_prompts.py` | Loading the production prompts; a drift detector on `app.py` constants. |
| `test_config.py` | `EVAL_JUDGE_MODEL` / `OPENAI_API_KEY` handling. |
| `test_openai_client.py` | Request shape, output extraction, retry and backoff, error messages. |
| `test_targets.py` | The payload mirrors the backend exactly; image encoding; `--model` is used. |
| `test_judge.py` | Judge prompt rules, strict verdict parsing, contradiction detection, judge request. |
| `test_runner.py` | Pass/fail/error classification, ordering, concurrency limit, callbacks. |
| `test_results.py` | Aggregation, pass-rate semantics, exit codes, results JSON. |
| `test_report.py` | Terminal rendering: markup-injection safety, one-line status rows, pure-ASCII output with aligned panels. |
| `test_terminal.py` | Unicode vs ASCII detection (locale, coerced `C.UTF-8`, encodings, Windows, overrides). |
| `test_theme.py` | Palette contrast on white and black, no loud ANSI colours, Rich's built-in colours overridden. |
| `test_logfile.py` | The full report: location, naming, no overwrites, full panels, plain text, charset. |
| `test_start_demo.py` | `start_demo.sh` syntax, help, option errors and interpreter checks (never creates a venv). |
| `test_demo.py` | The fake data is valid and exercises every outcome; stub validation. |
| `test_cli.py` | End-to-end CLI: demo, a live run against a fake OpenAI, usage errors, dry run, charset handling through real stdout/stderr streams. |

These tests are separate from the backend's own tests in `server/tests/`, which are untouched. The suite
passes across the dependency range `requirements.txt` allows (tested with Rich 13.0, 14.2 and 15.0, and
httpx 0.27 and 0.28).

## Code map and extension points

```
evals/
├── lens_evals/
│   ├── cli.py            # argparse entry point; wires everything; exit codes
│   ├── dataset.py        # EvalCase, Task, JSON schema validation, filters
│   ├── prompts.py        # reads production prompts + app.py constants (read-only)
│   ├── config.py         # EVAL_JUDGE_MODEL / OPENAI_API_KEY
│   ├── openai_client.py  # tiny async Responses API client with retries
│   ├── targets.py        # Target protocol + OpenAIVisionTarget (model under test)
│   ├── judge.py          # Judge protocol + LLMJudge, prompt, schema, verdict parsing
│   ├── runner.py         # run_suite(cases, target, judge) → SuiteResult
│   ├── results.py        # CaseResult / SuiteResult / Summary, JSON serialisation
│   ├── report.py         # Rich rendering (header, live progress, digest, detail panels, summary)
│   ├── logfile.py        # writes the full plain-text report (default /tmp/lens-evals)
│   ├── terminal.py       # Unicode/ASCII detection, glyph sets, ASCII-safe console
│   ├── theme.py          # colour palette (soft, light/dark-safe) + Rich style overrides
│   └── demo.py           # StubTarget / StubJudge over demo/demo_cases.json
├── start_demo.sh         # venv setup + unit tests + demo in one command
├── demo/demo_cases.json  # FAKE data for --demo
├── datasets/             # real cases.json + images/ go here
└── tests/
```

- **Multiple models under test (planned, not implemented).** Everything is keyed by `Target.name`.
  `run_suite` evaluates one target with one judge and returns a `SuiteResult` that records `model`. To add
  multi-model runs, make `--model` repeatable (`action="append"`), build one `OpenAIVisionTarget` per model
  (sharing one client and the judge), call `run_suite` for each, and add a comparison table to `report.py`.
  The runner, judge and results file need no changes.
- **Other targets.** Anything with a `name` and `async respond(case) -> str` is a target. An obvious one is
  an HTTP target that posts images to a deployed backend's `/describe` and `/read`, for end-to-end checks of
  a deployment.
- **Other judges.** Anything with a `name` and `async judge(case, response) -> Verdict`, e.g. a majority vote
  over several judge calls if judge variance turns out to matter.
- **New tasks.** Add a `Task` member, its prompt source in `prompts.TASK_SOURCES`, and its judging rules in
  `judge._TASK_RULES`.

## Limitations

- No real images or expected outputs exist yet, so no real eval has been run. Only the demo data is
  included.
- LLM judges are not perfectly deterministic. Keep `EVAL_JUDGE_MODEL` fixed when comparing runs, and look at
  the evidence for borderline failures. No `temperature` is sent, so reasoning models can be used as judges.
- The judge cannot catch errors that the checklist doesn't mention. Coverage is only as good as the
  `must_include` / `must_not_include` lists.
- Each case costs two API calls (target + judge). The target uses `detail: "high"` images, as production does.
