# Roadmap — Be My Lens (Guided Eye / عين الراشد)

A single-user Android MVP for AI image description for blind and low-vision Arabic speakers,
with a small FastAPI backend. This is a personal side project; every item below is work I plan
to do anyway, well over 20 hours.

Items are roughly ordered by priority. Estimates are my own and will shift.

---

## 1. Paginated PDF reading for blind users (large vertical slice)

Goal: let a blind user load a PDF and have it read out page by page, with navigation between
pages, within the same accessible flow used for single images.

- Add a PDF picker and a page renderer (PDFium / PdfRenderer / equivalent) in the Android app.
- Paginate: one image per PDF page, sent to the existing `/describe` / `/read` backend endpoints.
- Page navigation controls (next/previous, page indicator, jump to page), all TalkBack-friendly.
- Persist the current document and page across app restarts (Room or Preferences).
- New vertical slice in the test harnesses:
  - Android unit + integration tests for the PDF renderer and pager.
  - Backend contract tests confirming multi-page image uploads still return one session per image.
  - Eval cases (`evals/`) covering multi-page documents: text-heavy pages, mixed image/text pages,
    page-order integrity, and a "read this page" follow-up flow.
- Update `docs/` with the PDF workflow.

Estimated: largest single item on the roadmap; multiple sessions of work.

---

## 2. Backend security audit & fixes (concrete actions)

I explored `server/app.py`, `docker-compose.yml`, `Dockerfile`, the Android manifest, and the
network/repository layer. These are the clear issues and the fixes I plan:

| # | Issue | Finding | Fix |
|---|-------|---------|-----|
| 2.1 | Overly permissive CORS | `app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)` lets any site call the API. | Restrict `allow_origins` to the app's own origins / the deployed frontend; keep `*` off in production. |
| 2.2 | No backend authentication | `/describe`, `/read`, `/chat`, `/followup`, `/translate_text` accept unauthenticated calls. The `AuthGate` is client-side only; the backend enforces nothing. | Add a simple API-key or bearer-token check on model-backed routes (`/health` stays open). Fail closed with 401. |
| 2.3 | No rate limiting | No protection against abuse or OpenAI-key exhaustion. | Add a lightweight rate limiter (per-client IP or per-api-key) on POST endpoints. |
| 2.4 | No image size / type validation | Endpoints accept any upload with no cap; a very large or non-image file could be abused. | Enforce max upload size and validate the content type is an image before forwarding to the model. |
| 2.5 | In-memory sessions, no TTL | `SESSIONS: dict[str, Session]` grows without bound and sessions never expire. | Add session TTL and a bounded store, or evict old sessions. |
| 2.6 | Debug error details on screen | `LensViewModel.errorMessage()` shows class names + error messages on-screen in `DEBUG` builds. | Strip debug detail from release builds; keep short fallback strings only. |
| 2.7 | `android:allowBackup="true"` | `AndroidManifest.xml` allows app data backup via adb, exposing local state. | Set `android:allowBackup="false"` for release. |
| 2.8 | Exported `JieshuoEntryActivity` with broad intent filters | Exported activity accepts `image/*` and custom `DESCRIBE_IMAGE` actions from any app. | Keep export (screen-reader integration needs it), but harden intent validation (already validates scheme/MIME) and log a warning on unexpected inputs. |
| 2.9 | Debug HTTP logging | `LensRepository` uses `HttpLoggingInterceptor.Level.BASIC` in `DEBUG`, logging request URLs/headers. | Keep at `NONE` or `BASIC` only in debug; ensure no Authorization/cookie headers are logged. |
| 2.10 | No HTTPS enforcement / security headers | Backend runs plain HTTP behind the proxy; no `Strict-Transport-Security` or equivalent. | Enforce HTTPS at the proxy/ingress layer and set secure cookies if any are added later. |

Tests: add security-focused backend tests (rate limit returns 429, bad API key returns 401, oversized
image returns 413, CORS preflight is restricted, session expiry) and assert `allowBackup=false`
in the manifest test.

Estimated: several sessions.

---

## 3. Call-home mechanism for backend error collection

Goal: when things go wrong on the deployed backend, I (the maintainer) get enough diagnostic
signal to fix them — without collecting users' images or personal data.

- A small `/_internal/healthz`-style or error-reporting path the backend calls when it hits
  500/502 failures, sending: endpoint, status code, anonymised error class, timestamp, session
  id (not the image), and app version — never the image bytes or OCR text.
- Opt-in via an env var (`ENABLE_ERROR_REPORTING=1`) so it's off by default and explicit.
- Destination: a simple endpoint I control (or log to the same observability sink as the
  dashboard), over HTTPS.
- Unit tests verifying the payload shape and that images are never included.
- Docs entry explaining what is and isn't sent.

Estimated: ~1 session.

---

## 4. Analytics for feature usage

Goal: know which functions users actually use (describe vs read vs chat vs follow-up vs
translate-text) so I can prioritise.

- Anonymous counters in the backend: increment per-endpoint, per-day, no user ids, no image
  data, no personal data.
- Expose a read-only `/metrics` or `/analytics/summary` endpoint (authenticated, see 2.2).
- Android side: log which flow was triggered (describe/read/chat/followup/translate) —
  counts only, no image content.
- Opt-in toggle in settings (`Settings > Share usage statistics`), off by default.
- Unit + backend tests for the counters; contract that analytics never records images/text.

Estimated: ~1–2 sessions.

---

## 5. Analytics + deployment-management dashboard

Goal: a single web page to view usage analytics and manage the deployed backend.

- Dashboard backend: read the analytics counters and error reports from (3) and (4).
- Simple server-rendered or static frontend showing: endpoint usage over time, error rate,
  top errors, last deploy marker, health status.
- Deployment management controls: trigger a redeploy / restart (if the hosting platform exposes
  an API), view current `OPENAI_MODEL`, toggle `ENABLE_ERROR_REPORTING` and analytics opt-in
  state at runtime (via env or a small config store).
- Auth for the dashboard (separate from the app API key).
- Deploy on the same Render service or a companion service behind the same proxy.

Estimated: multiple sessions; depends on 2, 3, 4.

---

## 6. Other obvious work the app needs

These came out of reading the code and tests:

- **CI pipeline** — none exists. Add GitHub Actions: run `./run-tests.sh` on push/PR (backend,
  Android Robolectric, evals unit tests), and fail on secrets in history.
- **LICENSE visibility** — `LICENSE` is MIT and now tracked on the default branch; keep it there.
- **README plans section** — the job submission guide recommends visible plans; this ROADMAP.md
  serves that, plus open GitHub issues for individual items.
- **Android `targetSdk` / dependencies** — compileSdk 35, targetSdk 35; keep dependencies current
  (Firebase BoM pinned to 33.x because of Kotlin 2.0 — revisit when upgrading Kotlin).
- **Proguard/minify** — `isMinifyEnabled = false` for release; enable and test obfuscation.
- **No releases / no deployment docs for the Android APK** — `docs/deployment.md` covers the
  backend only; add APK/release notes workflow.
- **English prompt locale** — `server/prompts/en/` exists but is unused; decide whether to ship
  a language toggle or keep Arabic-only (docs currently say Arabic only).
- **Session persistence** — sessions are lost when the backend restarts; consider a lightweight
  store if follow-up continuity matters across deploys.
- **`google-services.json`** is committed with dummy values — keep it that way; never add real
  Firebase credentials.

Estimated: several sessions spread across the life of the project.

---

## How I'll track it

Each item above maps to one or more GitHub issues in this repo. As I work, I'll close issues and
update this file. Commits stay real and unsquashed, with the email linked to my GitHub account,
so reviewers can see the history.