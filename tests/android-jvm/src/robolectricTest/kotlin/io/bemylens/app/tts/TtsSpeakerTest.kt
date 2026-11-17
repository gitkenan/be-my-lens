package io.bemylens.app.tts

import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import io.bemylens.app.testing.TtsTestDevice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowTextToSpeech
import java.util.Locale

/**
 * TtsSpeaker, the single voice of the app: it reads every answer aloud, including the
 * ones Jieshuo requests. Uses the real speaker, settings store and engine discovery on a
 * Robolectric device.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class TtsSpeakerTest {
    @get:Rule
    val device = TtsTestDevice()

    private val store by lazy { SharedPreferencesTtsSettingsStore(device.context) }

    private fun speaker() = TtsSpeaker.getInstance(device.context)

    private fun arabicVoice(name: String, country: String): Voice {
        // Locale(String, String) is deprecated since Java 19; Builder is the documented replacement.
        val locale = Locale.Builder().setLanguage("ar").setRegion(country).build()
        return Voice(name, locale, Voice.QUALITY_HIGH, Voice.LATENCY_NORMAL, false, emptySet())
    }

    @Test
    fun answerRequestedBeforeTheEngineIsReadyIsSpokenOnceItIs() {
        val speaker = speaker()
        speaker.speak("باب أحمر عليه لافتة خروج.")
        assertEquals(emptyList<String>(), device.spoken())

        device.finishStarting()

        assertEquals(listOf("باب أحمر عليه لافتة خروج."), device.spoken())
    }

    @Test
    fun eachAnswerInterruptsTheOneBeingSpoken() {
        val speaker = speaker()
        device.finishStarting()

        speaker.speak("first")
        speaker.speak("second")

        assertEquals(listOf("first", "second"), device.spoken())
        assertEquals(TextToSpeech.QUEUE_FLUSH, shadowOf(device.engine).queueMode)
    }

    @Test
    fun stopDiscardsAnAnswerStillWaitingForTheEngine() {
        // JieshuoEntryActivity stops speech when a newer request arrives.
        val speaker = speaker()
        speaker.speak("stale answer")

        speaker.stop()
        device.finishStarting()

        assertEquals(emptyList<String>(), device.spoken())
    }

    @Test
    fun engineSpeaksArabic() {
        speaker()

        device.finishStarting()

        assertEquals("ar", shadowOf(device.engine).currentLanguage.language)
    }

    @Test
    fun settingsStateReflectsEngineStartup() {
        val acme = device.installEngine("com.acme.tts", "Acme TTS")
        val speaker = speaker()
        assertFalse(speaker.state.value.isInitialised)
        assertFalse(speaker.state.value.isReady)

        device.finishStarting()

        val state = speaker.state.value
        assertTrue(state.isInitialised)
        assertTrue(state.isReady)
        assertEquals(listOf(acme), state.engines.map { it.componentName })
        assertNull(state.engineComponent)
    }

    @Test
    fun savedEngineIsUsedWhenStillInstalled() {
        val acme = device.installEngine("com.acme.tts", "Acme TTS")
        store.save(TtsSelection(engineComponent = acme))

        val speaker = speaker()
        device.finishStarting()

        assertEquals("com.acme.tts", device.requestedEnginePackage())
        assertEquals(acme, speaker.state.value.engineComponent)
    }

    @Test
    fun savedEngineThatWasUninstalledFallsBackToSystemDefaultAndIsForgotten() {
        store.save(TtsSelection(engineComponent = "com.removed.tts/com.removed.tts.TtsService", voiceId = "v:ar"))

        speaker()

        assertNull(device.requestedEnginePackage())
        assertNull(store.load().engineComponent)
    }

    @Test
    fun engineThatFailsToStartFallsBackToSystemDefault() {
        val acme = device.installEngine("com.acme.tts", "Acme TTS")
        store.save(TtsSelection(engineComponent = acme))
        val speaker = speaker()
        val failingEngine = device.engine
        speaker.speak("answer")

        device.finishStarting(failingEngine, TextToSpeech.ERROR)
        val fallbackEngine = device.engine
        device.finishStarting(fallbackEngine)

        assertNotSame(failingEngine, fallbackEngine)
        assertNull(device.requestedEnginePackage(fallbackEngine))
        assertNull(store.load().engineComponent)
        assertEquals(listOf("answer"), device.spoken(fallbackEngine))
        assertTrue(speaker.state.value.isReady)
    }

    @Test
    fun lateStartupCallbackFromAReplacedEngineIsIgnored() {
        val acme = device.installEngine("com.acme.tts", "Acme TTS")
        val speaker = speaker()
        val defaultEngine = device.engine
        speaker.selectEngine(acme)
        val acmeEngine = device.engine
        speaker.speak("answer")

        device.finishStarting(defaultEngine)

        assertFalse("a replaced engine must not mark the speaker ready", speaker.state.value.isReady)
        assertEquals(emptyList<String>(), device.spoken(defaultEngine))

        device.finishStarting(acmeEngine)

        assertEquals(listOf("answer"), device.spoken(acmeEngine))
        assertEquals(acme, store.load().engineComponent)
    }

    @Test
    fun onlyArabicVoicesAreOfferedAndTheChosenOneIsAppliedAndRemembered() {
        val saudi = arabicVoice("ar-x-sfg-local", "SA")
        val egyptian = arabicVoice("ar-x-egy-local", "EG")
        listOf(saudi, egyptian, Voice("en-us-x", Locale.US, Voice.QUALITY_HIGH, Voice.LATENCY_NORMAL, false, emptySet()))
            .forEach(ShadowTextToSpeech::addVoice)
        val speaker = speaker()
        device.finishStarting()

        val offered = speaker.state.value.voices.map { it.voiceId }
        speaker.selectVoice("ar-x-sfg-local:ar-SA")

        assertEquals(listOf("ar-x-egy-local:ar-EG", "ar-x-sfg-local:ar-SA"), offered)
        assertEquals(saudi, shadowOf(device.engine).currentVoice)

        // After a restart the saved voice is applied as soon as the engine is ready.
        device.forgetSpeaker()
        speaker()
        device.finishStarting()

        assertEquals(saudi, shadowOf(device.engine).currentVoice)
    }

    @Test
    fun goingBackToTheEngineDefaultVoiceRestartsTheEngine() {
        ShadowTextToSpeech.addVoice(arabicVoice("ar-x-sfg-local", "SA"))
        val speaker = speaker()
        device.finishStarting()
        speaker.selectVoice("ar-x-sfg-local:ar-SA")
        val withChosenVoice = device.engine

        speaker.selectVoice(null)

        assertNotSame(withChosenVoice, device.engine)
        assertNull(store.load().voiceId)
    }
}
