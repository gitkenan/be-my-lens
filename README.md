# Be My Lens

`Be My Lens` is a single-user Android MVP for AI image description. The app can take a photo or pick one from the gallery, send it to a small backend, return a description, and support follow-up questions about the same image.

## What is included

- Android app scaffold in `app/`
- Minimal FastAPI backend in `server/`
- Follow-up chat bound to the current image session
- Android text-to-speech playback for responses

## Android app

Open the repo in Android Studio and let it import the Gradle project.

Backend URL configuration is read by Gradle in this order:

- `API_BASE_URL` in `local.properties`
- Gradle property `API_BASE_URL`
- Environment variable `API_BASE_URL`
- Fallback: `http://10.0.2.2:8000/`

Use the hosted backend for normal device testing:

```properties
API_BASE_URL=https://be-my-lens.planverse.io/
```

For a local backend on the Android emulator, use:

```properties
API_BASE_URL=http://10.0.2.2:8000/
```

For a local backend on a physical USB-connected Android device, use:

```properties
API_BASE_URL=http://127.0.0.1:8000/
```

Then forward the phone port to the laptop:

```bash
adb reverse tcp:8000 tcp:8000
```

`local.properties` is intentionally ignored by Git because it is machine-specific.

## Backend

Create a virtual environment and install the server dependencies:

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`, then run:

```bash
uvicorn app:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Tests

All test suites (backend, Jieshuo plugins, Android) run locally and never call OpenAI.
One script sets everything up and runs them:

```bash
./run-tests.sh              # everything that can run on this machine
./run-tests.sh backend      # one suite (see ./run-tests.sh list)
./run-tests.sh --coverage   # with a combined coverage report
./run-tests.sh doctor       # check Python, JDK, Gradle, Android SDK and network
```

See `docs/testing.md` for what each suite covers, coverage, CI, and the shared API
contract in `contract/`.

## Render deployment

Use a Render Web Service with:

- Root Directory: `server`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Environment: `OPENAI_API_KEY` and optionally `OPENAI_MODEL`

Current hosted endpoint:

```text
https://be-my-lens.planverse.io/
```

## API contract

The machine-readable version, checked by both the app and backend tests, is
`contract/api-contract.json`.

- `POST /describe`
  - multipart field: `image`
  - response: `sessionId`, `description`
- `POST /read`
  - multipart field: `image`
  - response: `sessionId`, `contents`
- `POST /chat`
  - multipart fields: `image`, `question`
  - response: `sessionId`, `answer`
- `POST /followup`
  - json body: `sessionId`, `question`
  - response: `answer`
- `POST /translate_text`
  - json body: `text`
  - response: `answer`

Errors are returned as JSON `{"detail": "..."}` with an Arabic message:

- `400`: empty image, question or text
- `404`: unknown or expired `sessionId` (sessions are lost when the backend restarts)
- `422`: missing or malformed fields
- `500`: backend misconfigured (`OPENAI_API_KEY` not set)
- `502`: the model service failed: it returned an error, timed out, was unreachable, or sent an unusable reply

## Notes

- Arabic is the only supported language, in both the app and the backend. `server/prompts/en/` is an unused reference for future expansion; see `server/prompts/README.md`.
- The backend keeps sessions in memory only.
- No authentication, sync, or persistence is included.
- Free hosted services may cold-start after idle periods.

## WSL and Windows workflow

The WSL checkout is the canonical repo for command-line work:

```text
/home/keenan/be-my-lens
```

Android Studio currently runs the Windows copy:

```text
C:\Users\Keenan\be-my-lens
```

This repo includes a one-way sync helper:

```bash
scripts/sync-to-windows.sh
```

It copies the WSL repo to the Windows copy while excluding `.git`, IDE files, build outputs, local properties, secrets, APKs, screenshots, and other local artifacts.

The WSL repo is configured locally to run the sync after each commit via:

```bash
git config core.hooksPath .githooks
```

If a fresh clone needs the same behavior, run that command once.
