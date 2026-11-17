package io.bemylens.app.tts

import io.bemylens.app.testing.TtsTestDevice
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Engine discovery through PackageManager and the saved engine/voice in SharedPreferences. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 35])
class TtsSettingsPersistenceTest {
    @get:Rule
    val device = TtsTestDevice()

    @Test
    fun installedEnginesAreListedByLabel() {
        // Package order is the reverse of label order, so only sorting by label passes.
        val zebra = device.installEngine("com.aaa.tts", "Zebra Voice")
        val acme = device.installEngine("com.zzz.tts", "Acme TTS")

        val engines = TtsEngines.installed(device.context)

        assertEquals(
            listOf(
                TtsEngineOption(componentName = acme, packageName = "com.zzz.tts", label = "Acme TTS"),
                TtsEngineOption(componentName = zebra, packageName = "com.aaa.tts", label = "Zebra Voice"),
            ),
            engines,
        )
    }

    @Test
    fun noInstalledEnginesMeansAnEmptyList() {
        assertEquals(emptyList<TtsEngineOption>(), TtsEngines.installed(device.context))
    }

    @Test
    fun savedSelectionSurvivesAnAppRestart() {
        SharedPreferencesTtsSettingsStore(device.context)
            .save(TtsSelection(engineComponent = "com.acme.tts/com.acme.tts.TtsService", voiceId = "ar-x-sfg-local:ar-SA"))

        val reloaded = SharedPreferencesTtsSettingsStore(device.context).load()

        assertEquals(TtsSelection("com.acme.tts/com.acme.tts.TtsService", "ar-x-sfg-local:ar-SA"), reloaded)
    }

    @Test
    fun choosingSystemDefaultsClearsTheSavedSelection() {
        val store = SharedPreferencesTtsSettingsStore(device.context)
        store.save(TtsSelection(engineComponent = "com.acme.tts/com.acme.tts.TtsService", voiceId = "v:ar"))

        store.save(TtsSelection())

        assertEquals(TtsSelection(), SharedPreferencesTtsSettingsStore(device.context).load())
    }

    @Test
    fun freshInstallHasNoSelection() {
        assertEquals(TtsSelection(), SharedPreferencesTtsSettingsStore(device.context).load())
    }
}
