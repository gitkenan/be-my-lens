# Authentication (Google sign-in gate)

The app requires a Google sign-in before the main UI is shown. This is a
**client-side gate only**: it changes nothing about the API contract, and the
backend still accepts unauthenticated requests. Its purpose is to put an
account in front of the app now, so per-user features and backend enforcement
can be added later without reworking the UI.

## How it works

Stack: Firebase Authentication (Google provider) + AndroidX Credential Manager.

- `app/src/main/java/io/bemylens/app/auth/AuthGate.kt` — the whole feature.
  `AuthGate` is a composable that watches `FirebaseAuth` state: signed out, it
  renders an Arabic sign-in screen; signed in, it renders its `content` slot.
  `BeMyLensApp.kt` wraps `LensScreen` in it.
- The sign-in button runs the Credential Manager "Sign in with Google" flow
  (`GetGoogleIdOption`) and passes the resulting Google ID token to
  `FirebaseAuth.signInWithCredential`. Dismissing the account sheet returns to
  the sign-in screen silently; real failures show `error_sign_in_failed`.
- Firebase persists the session on-device, so sign-in happens once per
  install. There is no sign-out UI; clear app data to sign out.
- `JieshuoEntryActivity` is **not** gated — screen-reader invocations work
  whether or not the user ever signed in.

## Firebase configuration

- Firebase project: `be-my-lens` (Google provider enabled under
  Authentication → Sign-in method).
- `app/google-services.json` — committed on purpose; the values in it are
  client identifiers, not secrets. The google-services Gradle plugin generates
  `R.string.default_web_client_id` from it, which `AuthGate` uses as the
  `serverClientId`. Never hardcode the client ID.
- Gradle wiring: `com.google.gms.google-services` plugin (root + app),
  Firebase BoM + `firebase-auth`, `androidx.credentials`, `googleid`, and
  `kotlinx-coroutines-play-services`. The BoM is pinned to 33.x because 34.x
  needs Kotlin 2.2+ and the project is on Kotlin 2.0 (see comment in
  `app/build.gradle.kts`).

## SHA-1 fingerprints

Google verifies the APK's signing certificate server-side, so every keystore
that produces installed builds must have its SHA-1 registered in Firebase
(Project settings → General → the Android app → Add fingerprint). The new
Firebase console does not prompt for this during registration, but sign-in
fails without it. Debug keystores are per-machine, not per-repo:

- WSL builds (`./gradlew installDebug`): `~/.android/debug.keystore`
  ```
  keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android | grep SHA1
  ```
- Android Studio on Windows: `C:\Users\Keenan\.android\debug.keystore`
  ```powershell
  & "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe" -list -v -keystore "$env:USERPROFILE\.android\debug.keystore" -alias androiddebugkey -storepass android | Select-String SHA1
  ```

Register both. Adding a fingerprint takes effect server-side; no rebuild or
`google-services.json` re-download is needed.

## Troubleshooting

- Sign-in sheet never appears / immediate failure: SHA-1 of the keystore that
  built the installed APK is missing in Firebase, or the Google provider is
  disabled.
- `error_sign_in_failed` after picking an account: check Logcat for the
  `BeMyLens` tag — `AuthGate` logs the underlying exception.
- Device needs Google Play services and a Google account.

## Deliberately out of scope (for now)

When auth needs to actually protect the backend:

1. OkHttp interceptor in `LensRepository` attaching
   `Authorization: Bearer <Firebase ID token>` (from
   `currentUser.getIdToken(false)`, which auto-refreshes).
2. FastAPI dependency in `server/app.py` verifying the token (e.g.
   `google-auth`'s `verify_firebase_token` with project ID `be-my-lens`),
   applied to `/describe`, `/read`, `/chat`, `/followup` — keep `/health`
   open.
3. A signed-in check (or its own sign-in path) in `JieshuoEntryActivity`.
