# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Be My Lens is a single-user Android MVP for AI image description aimed at blind and low-vision users. The user-facing display name is "Guided Eye" (Arabic: عين الراشد) — deliberately distinct from the Be My Eyes app; "Be My Lens" remains the repo/code name, and technical identifiers (`io.bemylens.app`, intent actions, theme names) must not be renamed. Three parts:

- `app/` — Kotlin/Jetpack Compose Android app (Retrofit, Moshi, Coil). Takes/picks a photo, sends it to the backend, speaks the result via Android TTS, supports follow-up chat about the same image.
- `server/` — FastAPI backend (`server/app.py`, single file) that calls the OpenAI Responses/Chat Completions APIs. Sessions are in-memory only; permissive CORS; no auth or persistence (the app's Google sign-in is a UI gate only — see `docs/auth.md`).
- `prototypes/jieshuo/` + `dist/jieshuo-lua/` — Lua scripts for the Jieshuo screen reader that capture a screenshot and launch the app via an intent contract. `prototypes/` holds the diagnostic harness; `dist/` holds standalone tester-facing actions.

The product is Arabic-first: app strings, backend prompts, and backend error messages are Arabic by default (`PROMPT_LOCALE` env var, prompts in `server/prompts/{ar,en}/`).

## Commands

Android (from repo root):
- `./gradlew assembleDebug` — build debug APK (output: `app/build/outputs/apk/debug/app-debug.apk`)
- `./gradlew test` — run JVM unit tests
- `./gradlew :app:testDebugUnitTest --tests io.bemylens.app.data.LensJsonTest` — Retrofit/Moshi regression tests; run these after any networking or API model change
- `./gradlew connectedAndroidTest` — instrumentation tests (needs emulator/device)

Backend:
- `cd server && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` — setup
- `cd server && uvicorn app:app --reload` — run at `http://127.0.0.1:8000` (requires `OPENAI_API_KEY` in `server/.env`, start from `.env.example`)
- `curl http://127.0.0.1:8000/health` — health check
- No backend tests exist yet; if added, use pytest under `server/tests/` and document the command here.

Device networking:
- `adb reverse tcp:8000 tcp:8000` — lets a USB-connected device reach a local backend via `http://127.0.0.1:8000/`

## Backend URL wiring

The app reads the backend URL from `BuildConfig.API_BASE_URL`, generated in `app/build.gradle.kts` from (in order): `API_BASE_URL` in `local.properties` → Gradle property → environment variable → fallback `http://10.0.2.2:8000/` (emulator). Hosted backend: `https://be-my-lens.planverse.com/`. `local.properties` is git-ignored and machine-specific.

## API contract (backend ⇄ app)

Endpoints in `server/app.py`, mirrored by `LensApi.kt`/`LensRepository.kt`:
- `POST /describe` — multipart `image` → `{sessionId, description}` (Responses API + describe prompt)
- `POST /read` — multipart `image` → `{sessionId, contents}` (OCR-style read prompt)
- `POST /chat` — multipart `image` + form `question` → `{sessionId, answer}` (Chat Completions, used for custom prompts)
- `POST /followup` — JSON `{sessionId, question}` → `{answer}` (replays last 8 transcript turns + the session image)

Sessions live only in the server process; a restart or Render cold start invalidates `sessionId`s.

## Android architecture

- `MainActivity` + `ui/LensViewModel` — main Compose UI; single `LensUiState` StateFlow driving image selection, loading, answer, and chat state.
- `auth/AuthGate.kt` — Google sign-in gate (Firebase Auth + Credential Manager) wrapping the main UI; client-side only, does not protect the backend, and `JieshuoEntryActivity` bypasses it. Requires the building machine's debug-keystore SHA-1 registered in Firebase. Details: `docs/auth.md`.
- `data/` — `LensRepository` (OkHttp/Retrofit, compresses and uploads images via `ImageUtils`), `LensApi` (Retrofit interface), `LensJson` (custom Moshi converter factory — has a dedicated regression test, don't change casually).
- `JieshuoEntryActivity` — exported Activity for external callers (screen readers). Minimal UI, separate from the main flow; copies the incoming image URI into app cache, runs the pipeline, speaks the result, and guards against stale results when relaunched quickly.
- `integration/` — `ExternalIntegrationContract` (action `io.bemylens.app.action.DESCRIBE_IMAGE`, modes `describe_screen` / `focused_item` / `read_text` / `custom_prompt`, extras `mode`/`prompt`/`autoSpeak`) and `ExternalImageIntentParser` (URI lookup order: `EXTRA_STREAM` → `io.bemylens.app.extra.IMAGE_URI` → `Intent.data`). Full contract with ADB test commands: `docs/jieshuo-integration.md`; Jieshuo Lua findings and device-test checklist: `docs/jieshuo-lua-prototype.md`.

## WSL / Windows workflow

This WSL checkout (`/home/keenan/be-my-lens`) is canonical for CLI work; Android Studio uses the Windows copy at `C:\Users\Keenan\be-my-lens`. A post-commit hook (`.githooks/post-commit`, enabled via `git config core.hooksPath .githooks`) runs `scripts/sync-to-windows.sh` to one-way sync WSL → Windows after each commit.

## Conventions

- Kotlin: 4-space indent, trailing commas where already used, composables in `PascalCase`, state holders as `*ViewModel`.
- Python: 4-space indent, type hints on public helpers, Pydantic models for request bodies.
- Concise imperative commit subjects (e.g. `Add image upload error state`).
- Never commit `server/.env`, `local.properties`, or real API keys. (`app/google-services.json` is committed on purpose — it holds client identifiers, not secrets.)
- See `AGENTS.md` for extended repository guidelines.
