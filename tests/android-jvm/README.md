# Android JVM harness

Runs Android tests on a plain JVM against the app's real sources, without the Android
Gradle Plugin, the Android SDK or an APK build:

- `test`: every test in `app/src/test/`, against an AGP-style mockable `android.jar`.
- `robolectricTest`: the harness-only suite in `src/robolectricTest/`, on a real Android
  framework (Robolectric, API 26 and 35). It covers the data layer and image pipeline,
  `LensViewModel`, text-to-speech and real Jieshuo intent delivery.

```bash
./run-tests.sh android                    # from the repo root; picks a Gradle for you
./gradlew -p tests/android-jvm check      # or directly
./gradlew -p tests/android-jvm check coverageReport -Pcoverage   # with JaCoCo coverage
```

Full documentation (what it compiles, how it stays faithful, known limits, CI) is in
[`docs/testing.md`](../../docs/testing.md#android-jvm-harness).
