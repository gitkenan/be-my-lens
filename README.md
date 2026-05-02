# Be My Lens

`Be My Lens` is a single-user Android MVP for AI image description. The app can take a photo or pick one from the gallery, send it to a small backend, return a description, and support follow-up questions about the same image.

## What is included

- Android app scaffold in `app/`
- Minimal FastAPI backend in `server/`
- Follow-up chat bound to the current image session
- Android text-to-speech playback for responses

## Android app

Open the repo in Android Studio and let it import the Gradle project.

Default backend URL:

- Android emulator: `http://10.0.2.2:8000/`

If you want to run the app against a physical device or different host, update `API_BASE_URL` in [app/build.gradle.kts](/home/keenan/be-my-lens/app/build.gradle.kts).

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

## API contract

- `POST /describe`
  - multipart field: `image`
  - response: `sessionId`, `description`
- `POST /followup`
  - json body: `sessionId`, `question`
  - response: `answer`

## Notes

- The backend keeps sessions in memory only.
- No authentication, sync, or persistence is included.
- I could not compile or run this in the current workspace because `java` and `gradle` are not installed here.
