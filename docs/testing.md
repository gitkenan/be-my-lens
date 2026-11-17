# Testing

Be My Lens has three test suites, one per moving part, plus a shared HTTP contract
between the app and the backend. Nothing calls the real OpenAI API: the backend suite
replaces the network hop to OpenAI with a local fake, and the other suites never
reach the backend at all.

| Suite | Location | What runs for real | What is faked |
| --- | --- | --- | --- |
| Backend | `server/tests/` | The FastAPI app over HTTP: validation, prompts, payloads, sessions, error handling | The HTTPS connection to OpenAI (`httpx` transport) |
| Jieshuo plugins | `tests/jieshuo/` | The shipped `.lua` files under Lua 5.3, writing real files | The Jieshuo/Android host the scripts run in |
| Android app | `app/src/test/`, run by AGP or by `tests/android-jvm/` | Retrofit/OkHttp/Moshi client, intent parsing, TTS selection rules | The backend (`MockWebServer`) |
| Android on Robolectric | `tests/android-jvm/src/robolectricTest/` | Repository, image pipeline, `LensViewModel`, TTS, real `Intent` delivery, on a real Android framework | The backend (`MockWebServer` as an HTTP proxy) |

## Running

Use `./run-tests.sh` from the repo root. It needs only bash, Python 3.10+ (for the
Python suites) and JDK 17+ (for the Android suites). It creates and maintains its own
virtualenv (`server/.venv`) and finds a usable Gradle itself:

```bash
./run-tests.sh                       # every suite that can run on this machine
./run-tests.sh backend jieshuo       # selected suites (also: android, android-unit, robolectric, agp, python)
./run-tests.sh --coverage            # plus a combined coverage report
./run-tests.sh doctor                # what can run here, and why not
./run-tests.sh --help                # all options
```

| Suite | What it runs | Needs |
| --- | --- | --- |
| `backend` | `server/tests` (pytest) | Python 3.10+ |
| `jieshuo` | `tests/jieshuo` (pytest + Lua 5.3) | Python 3.10+ |
| `android-unit` | `app/src/test` on the Android JVM harness | JDK 17+, Gradle 8.7+ |
| `robolectric` | the harness's Robolectric suite | JDK 17+, Gradle 8.7+ |
| `agp` | `app/src/test` through the real Android build | Android SDK (skipped, not failed, without one) |

How the script sets things up:

- **Python.** It picks a Python of at least 3.10 (preferring 3.12, which the Docker
  image uses) and creates `server/.venv`. If `python -m venv` is unavailable (e.g.
  Debian without `python3-venv`), it falls back to `uv` or `virtualenv`. Dependencies
  are reinstalled only when a requirements file changes.
- **Gradle** (`--gradle=auto`, the default), in this order:
  1. the repo wrapper (`./gradlew`), if its Gradle 8.7 is already downloaded;
  2. a local Gradle 8.7+, first on `PATH`, then the newest `/opt/gradle-*`;
  3. the wrapper, downloading Gradle 8.7.

  It prints which one it chose and why. Force a choice with `--gradle=wrapper`,
  `--gradle=local` or `--gradle=/path/to/gradle`. The wrapper is always invoked through
  `sh`, so a checkout that lost `gradlew`'s executable bit still works.
- **Results.** JUnit XML for every suite lands in `build/test-results/<suite>/`. The run
  ends with a pass/fail/skip table, and the exit status is non-zero if any suite failed.
  Arguments after `--` go to pytest or Gradle, e.g.
  `./run-tests.sh backend -- -k followup` or
  `./run-tests.sh robolectric -- --tests '*TtsSpeakerTest'`.

Running a suite by hand, without the script:

```bash
server/.venv/bin/pip install -r server/requirements-dev.txt -r tests/jieshuo/requirements.txt
server/.venv/bin/python -m pytest server/tests tests/jieshuo -q   # backend + jieshuo
./gradlew -p tests/android-jvm check                             # android-unit + robolectric
./gradlew :app:testDebugUnitTest                                  # agp (needs the Android SDK)
```

For `app/src/test`, the real Android build remains the final word. See
[Android JVM harness](#android-jvm-harness) and [CI](#ci).

## Coverage

`./run-tests.sh --coverage` measures each suite with the usual tool for its language and
prints one combined report (also saved to `build/coverage/summary.md`):

| Area | Tool | Details |
| --- | --- | --- |
| Backend | coverage.py via pytest-cov, lines and branches (`.coveragerc`) | `build/coverage/backend-html/` |
| Jieshuo plugins | built into the harness (`tests/jieshuo/lua_coverage.py`) | `build/coverage/lua.json` |
| Android | JaCoCo on both harness suites (`-Pcoverage`, `coverageReport`) | `tests/android-jvm/build/reports/jacoco/coverageReport/html/` |

- **Lua.** No LuaCov is needed. Executable lines are read from the Lua compiler's own
  line tables (parsed from `string.dump` bytecode), and hits are recorded by a
  `debug.sethook` line hook. This includes callbacks Jieshuo makes after the script
  returns.
- **Android, unmeasured files.** Files the harness cannot compile (the Compose UI,
  `JieshuoEntryActivity`, `MainActivity`, `AuthGate`) are listed as uncovered. Their
  size is estimated from their code lines, scaled to JaCoCo's line definition using
  the measured files. Totals that include them are marked as estimates.

## Approach

Tests go through the widest boundary that still runs fast and offline, and fake only
what sits outside the system:

- Backend tests call endpoints with `TestClient` and assert on HTTP responses and on
  the requests that would have gone to OpenAI. No internal function is patched.
  `FakeOpenAI` (`server/tests/support.py`) is autouse, so a test cannot reach the real
  API even if a developer's `server/.env` holds a real key. It is also strict: a model
  call the test did not queue a reply for fails the test.
- Multi-step behaviour is tested as the app uses it, for example describe, then
  several follow-ups, then checking the history the model received.
- Android client tests run the real Retrofit interface and JSON converter against
  `MockWebServer`, so request encoding and response parsing are both covered.

## Shared HTTP contract

`contract/api-contract.json` lists each endpoint's path, request fields and an example
response. Both sides test against it:

- `server/tests/test_api_contract.py`: the backend accepts these requests and returns
  exactly these response fields. It also checks that every POST route is listed.
- `app/src/test/.../data/LensApiContractTest.kt`: the app sends these requests and
  parses these responses. It also checks that every `LensApi` method is listed.

Renaming a field on one side fails that side's test, and updating the contract then
fails the other side's test until the two codebases agree. Change the contract, the
backend and the app together.

## Jieshuo plugin harness

`tests/jieshuo/jieshuo_host.py` recreates the AndroLua environment the plugins run in:
`require "import"`, the `this` service, the focused `node`, `File` and
`FileOutputStream` backed by a temp directory, `Toast`, and the asynchronous
`getScreenShot` callbacks. The Jieshuo-specific APIs follow what was confirmed on a
device (see `docs/jieshuo-lua-prototype.md`). `startActivity` resolves explicit
intents against the exported activities in the real `AndroidManifest.xml`, so a wrong
package or class name fails to launch, just as it would on a phone.

Expected values come from the app's own sources (`android_contract.py` reads
`ExternalIntegrationContract.kt`, the manifest and `build.gradle.kts`). Renaming an
extra, mode or action in Kotlin therefore fails these tests until the Lua plugins are
updated.

The tests cover:

- **Happy paths.** Each plugin launches Be My Lens with the right mode, a readable PNG
  and a URI read grant. The text plugin sends the focused text and never captures a
  screenshot.
- **Failures a blind user would hit.** Storage fallbacks (external cache, internal
  cache, `/sdcard`), failed or unavailable screenshots, compression failures, no
  shareable URI, Be My Lens not installed, and no focused text. In each case the
  user hears why, nothing crashes, and no file handle is left open.
- **Every script is discovered automatically.** `test_jieshuo_plugin_contract.py` runs
  every `.lua` file in `dist/jieshuo-lua/` and `prototypes/jieshuo/` and checks its
  launch against the Android contract. A new plugin is covered without writing a test.

`JieshuoPluginCommandsTest.kt` is the Android half of the same hand-off: it feeds the
payloads the plugins send into the app's real intent parser.

The harness cannot prove Jieshuo itself behaves as modelled. Keep using the real-device
checklist in `docs/jieshuo-lua-prototype.md` before releasing plugin changes.

## Android JVM harness

`tests/android-jvm/` is a small standalone Gradle build that runs Android tests on a
plain JVM, against the app's **real** Kotlin sources compiled straight from
`app/src/main` (no copies). It needs no Android Gradle Plugin (AGP), Android SDK or APK
build. It has two test suites:

| Task | Tests | Android framework |
| --- | --- | --- |
| `test` | every file in `app/src/test/java`, the same tests AGP runs | AGP-style mockable `android.jar`: framework calls throw `not mocked` |
| `robolectricTest` | `tests/android-jvm/src/robolectricTest/`, harness-only | Robolectric: a real Android framework on the JVM, at API 26 (`minSdk`) and/or 35 (`targetSdk`) |

```bash
./gradlew -p tests/android-jvm check            # both suites
./gradlew -p tests/android-jvm test             # only app/src/test
./gradlew -p tests/android-jvm robolectricTest  # only the Robolectric suite
```

Any Gradle from 8.7 (the repo wrapper's version) works, including a locally installed
one (see [CI](#ci)). The first run downloads and caches about 170 MB of framework classes
for `test`, plus about 400 MB for `robolectricTest` (one framework per API level). After
that, runs take seconds plus compile time.

Downloads come from Maven Central, except a few small AndroidX artifacts that exist
only on Google's Maven repository: `androidx.test` (needed by Robolectric),
`androidx.lifecycle:lifecycle-viewmodel-android` and `androidx.annotation`.
`settings.gradle.kts` restricts Google's repository to exactly those groups.

### What the Robolectric suite covers

These tests run the unmodified production classes, driven from their real entry points:

- **Jieshuo hand-off** (`JieshuoIntentDeliveryTest`). Real `Intent`s are built the way
  the Lua plugins and the documented `adb` commands build them, sent through a `Parcel`
  round trip (as Android does between apps), and parsed through the app's Android
  adapter on API 26 and 35. This covers the `EXTRA_STREAM`, `IMAGE_URI` (as a `Uri` or
  a string) and `Intent.data` routes.
- **Data layer** (`LensRepositoryTest`). The real `LensRepository`, its OkHttp/Retrofit
  client and `ImageUtils` run against a fake backend. Real photos are decoded by
  Android's native graphics code, scaled to at most 1600 px and uploaded as JPEG. The
  tests also cover follow-up and translation requests, backend errors, and files that
  aren't images.
- **Main screen** (`LensViewModelTest`). The real `LensViewModel` is driven through
  describe, read, question and follow-up flows: session reuse, withdrawing a failed
  question, error messages in the app's own Arabic text, and starting over with a new
  photo.
- **Speech** (`TtsSpeakerTest`, `TtsSettingsPersistenceTest`). The real `TtsSpeaker`,
  engine discovery and saved settings. Covered cases:
  - an answer requested before the engine is ready is spoken once it is;
  - a newer request silences a stale one;
  - speech is in Arabic;
  - an uninstalled or failing engine falls back to the system default;
  - a late callback from a replaced engine is ignored;
  - only Arabic voices are offered, and the chosen voice is remembered across restarts.

### How it stays faithful without production changes

- **Mockable `android.jar`** (for `test`). The `mockableAndroidJar` task builds the same
  kind of `android.jar` AGP uses for unit tests, from Robolectric's `android-all` at API
  35 (`compileSdk`). A test that accidentally relies on real Android behaviour fails here
  just as it would under AGP.
- **Same versions.** The Kotlin version and library versions are read from the repo's
  `build.gradle.kts` files, so the two builds cannot drift apart.
- **Same working directory.** `test` runs from `app/`, as under AGP.
- **Generated `BuildConfig` and `R`.** AGP normally generates these. The harness
  generates `BuildConfig` with the same fields; its `API_BASE_URL` is
  `http://backend.be-my-lens.test/`, a host that can never resolve. It also generates
  `R.string` from `app/src/main/res/values/strings.xml`. In the Robolectric suite,
  `AppStringsApplication` serves the real text for those IDs, so
  `getString(R.string.x)` returns the app's actual strings without running `aapt2`.
- **Fake backend through a proxy.** `LensRepository` builds its own HTTP client, so
  `FakeBackend` installs `MockWebServer` as the JVM's default HTTP proxy and the app's
  unmodified client reaches it. A request that bypassed the proxy could not resolve the
  `.test` host, so nothing reaches a real server. This mirrors how the backend tests
  fake OpenAI at the transport layer.
- **Test-side reflection, only where a singleton needs it.** `TtsSpeaker` is a
  process-wide singleton, and Robolectric reuses the JVM between tests, so
  `TtsTestDevice` clears its private `instance` field between tests.

### What it compiles

- **Production sources.** The files listed in `appSourcesUnderTest` in
  `tests/android-jvm/build.gradle.kts`: the data layer, intent parsing, TTS and
  `LensViewModel`. Files using Compose (the screens, `JieshuoEntryActivity`,
  `MainActivity`, `AuthGate`) are not compiled.
- **Test sources.** `test` compiles every file in `app/src/test/java`.
  `robolectricTest` compiles `tests/android-jvm/src/robolectricTest/`.

When a new test needs another production file, add it to `appSourcesUnderTest`. Tests
that need Compose or Firebase can only run through AGP.

### Known limits

- Robolectric's native graphics start at API 28, so real-pixel image tests run on API
  35 only (API 26 would get fake 100x100 bitmaps). On API 26, decoding goes through
  `MediaStore` instead of `ImageDecoder`, and that branch is not covered with real
  images.
- Robolectric cannot decode an image from a file descriptor. Image tests therefore use
  `content://` URIs, as the photo picker provides. Jieshuo's copied `file://` images
  are opened via a file descriptor and then go through the same decode, scale and
  JPEG code.
- The harness `BuildConfig` is a debug build, so release-only behaviour (short error
  messages without debug detail) is not exercised.
- `android-all` contains hidden platform APIs that the SDK's `android.jar` does not.
  Code using one would compile here but not under AGP.
- The harness was verified with Gradle 8.14.3. The repo wrapper pins Gradle 8.7, and
  the build only uses APIs available in that version.

## CI

CI runs `./run-tests.sh`, using the tools installed on the machine and no Android SDK:

```bash
./run-tests.sh --gradle=local       # or leave the default: auto falls back to /opt/gradle-*
./run-tests.sh --gradle=local --coverage
```

- **Gradle.** CI uses the Gradle installed on the machine (currently
  `/opt/gradle-8.14.3`) rather than downloading the wrapper's distribution.
  `--gradle=local` requires that, while the default `auto` mode falls back to it when
  the wrapper's Gradle isn't already downloaded. `BML_GRADLE=/opt/gradle-8.14.3/bin/gradle`
  pins an exact install.
- **Reports.** Collect `build/test-results/**/*.xml` as JUnit reports, and
  `build/coverage/` for coverage runs.
- **Caches.** Cache `~/.gradle/caches` (the Android framework jars, about 600 MB) and
  `server/.venv` between runs, so warm runs need no large downloads.
- **Network.** First runs need PyPI, Maven Central, and Google's Maven repository for
  a few AndroidX artifacts. `./run-tests.sh doctor` checks all of these.
- **Java.** The machine needs JDK 17 or newer; the harness was verified with JDK 21.
- **The `agp` suite** is skipped automatically when no Android SDK is installed, and
  runs wherever one is.

## Not covered yet

No production code was changed to make code testable. What remains out of reach without
changing that rule:

- **`JieshuoEntryActivity`**: mode-to-endpoint routing, copying the received image,
  the stale-request guard, and error screens. Both halves around it are covered: the
  intents it receives (`JieshuoIntentDeliveryTest`) and the repository calls it makes
  (`LensRepositoryTest`). The Activity itself is built on Jetpack Compose, and running
  Compose needs the full AndroidX/Compose libraries and their compiled resources,
  which only AGP produces. Two options:
  - Run Robolectric through AGP. This needs test dependencies and
    `testOptions.unitTests.isIncludeAndroidResources = true` in
    `app/build.gradle.kts`, a build change.
  - Move `processCommand` into a plain class. This needs a small production change,
    after which the harness could test it directly.
- **Compose screens and `AuthGate`**: better suited to instrumented UI tests on a
  device or emulator.
- **Release-build behaviour and the API 26 image-decoding branch**: see Known limits
  above.
- **The real OpenAI API**, deliberately. The request shapes the backend builds are
  asserted, but not that OpenAI still accepts them.
