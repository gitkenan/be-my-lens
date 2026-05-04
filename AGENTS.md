# Repository Guidelines

## Project Structure & Module Organization

This repository contains an Android MVP and a small API backend. `app/` is the Kotlin Android module using Jetpack Compose, Retrofit, Moshi, and Coil. App source lives in `app/src/main/java/io/bemylens/app/`, with networking and image helpers in `data/`. Android resources live in `app/src/main/res/`.

`server/` contains the FastAPI backend, including image upload handling, OpenAI Responses API calls, and in-memory image sessions. Gradle configuration is at the repository root plus `app/build.gradle.kts`.

Add unit tests under `app/src/test/`, instrumentation tests under `app/src/androidTest/`, and backend tests under `server/tests/` if server behavior expands.

## Build, Test, and Development Commands

- `./gradlew assembleDebug`: build a debug APK.
- `./gradlew test`: run Android JVM unit tests when present.
- `./gradlew :app:testDebugUnitTest --tests io.bemylens.app.data.LensJsonTest`: run the Retrofit/Moshi regression tests.
- `./gradlew connectedAndroidTest`: run instrumentation tests on a connected emulator or device.
- `cd server && python -m venv .venv`: create the backend virtual environment.
- `source server/.venv/bin/activate`: activate it from the repo root.
- `cd server && pip install -r requirements.txt`: install backend dependencies.
- `cd server && uvicorn app:app --reload`: run the backend at `http://127.0.0.1:8000`.
- `curl http://127.0.0.1:8000/health`: verify the local backend is reachable.
- `adb reverse tcp:8000 tcp:8000`: let a USB-connected physical Android device reach a local backend through `http://127.0.0.1:8000/`.
- `scripts/sync-to-windows.sh`: manually sync the WSL checkout to the Windows Android Studio copy.

The Android backend URL is generated into `BuildConfig.API_BASE_URL`. Gradle reads `API_BASE_URL` from `local.properties`, then Gradle properties, then the environment, and finally defaults to `http://10.0.2.2:8000/`. The current hosted Render endpoint is `https://be-my-lens.onrender.com/`.

For Android Studio on Windows, the working copy is `C:\Users\Keenan\be-my-lens`. The WSL repo at `/home/keenan/be-my-lens` has `core.hooksPath` configured to `.githooks`, so commits run `.githooks/post-commit` and sync to Windows. A fresh clone needs `git config core.hooksPath .githooks` to enable that hook locally.

## Coding Style & Naming Conventions

Use Kotlin with 4-space indentation, trailing commas where already used, and idiomatic Compose naming: composables in `PascalCase`, state holders as `*ViewModel`, and data/API classes such as `DescribeResponse`.

Use Python 3 style in `server/app.py`: 4-space indentation, type hints for public helpers, and Pydantic models for request bodies.

## Testing Guidelines

Prefer focused tests around behavior with real risk: image compression, repository request construction, ViewModel state transitions, API parsing, and FastAPI errors. Name Kotlin tests after the class or feature, for example `LensViewModelTest.kt`. Name Python tests `test_*.py`.

Run the relevant Gradle test task before changing Android code. For networking or API model changes, run `./gradlew :app:testDebugUnitTest --tests io.bemylens.app.data.LensJsonTest`. For backend changes, add `pytest` when tests are introduced and document the command here.

## Commit & Pull Request Guidelines

The current history only shows `initial commit`, so use concise imperative commit subjects going forward, for example `Add image upload error state` or `Fix follow-up session handling`.

Pull requests should include a short summary, test results, linked issue if applicable, and screenshots or recordings for UI changes. Mention changes to `API_BASE_URL`, `.env.example`, or OpenAI model settings.

## Security & Configuration Tips

Never commit `server/.env`, `local.properties`, or real API keys. Start from `server/.env.example` and set `OPENAI_API_KEY` locally or in Render environment variables. The backend stores sessions in memory and has permissive CORS for MVP development, so follow-up sessions can disappear after process restarts or host cold starts.
