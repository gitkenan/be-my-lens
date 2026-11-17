package io.bemylens.app.testing

import android.content.ComponentName
import android.content.Context
import android.content.IntentFilter
import android.speech.tts.TextToSpeech
import io.bemylens.app.tts.TtsSpeaker
import org.junit.rules.ExternalResource
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowTextToSpeech
import org.robolectric.util.ReflectionHelpers

/**
 * The device's text-to-speech side, driven through Robolectric's TextToSpeech and
 * PackageManager shadows. The test decides when (and whether) an engine finishes
 * starting, which is how TtsSpeaker's race handling can be tested deterministically.
 */
class TtsTestDevice : ExternalResource() {
    val context: Context get() = RuntimeEnvironment.getApplication()

    // TtsSpeaker is a process-wide singleton and Robolectric reuses the JVM between
    // tests, so each test starts from "app just launched".
    override fun before() = forgetSpeaker()

    override fun after() = forgetSpeaker()

    /** Simulates the app process restarting: the next getInstance() builds a new speaker. */
    fun forgetSpeaker() {
        ReflectionHelpers.setStaticField(TtsSpeaker::class.java, "instance", null)
    }

    fun installEngine(packageName: String, label: String): String {
        val component = ComponentName(packageName, "$packageName.TtsService")
        val packageManager = shadowOf(context.packageManager)
        val service = packageManager.addServiceIfNotPresent(component)
        service.nonLocalizedLabel = label
        packageManager.addOrUpdateService(service)
        packageManager.addIntentFilterForService(component, IntentFilter(TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE))
        return component.flattenToString()
    }

    /** The TextToSpeech instance TtsSpeaker created most recently. */
    val engine: TextToSpeech get() = ShadowTextToSpeech.getLastTextToSpeechInstance()!!

    /** The engine package a TextToSpeech was created for; null means the system default. */
    fun requestedEnginePackage(tts: TextToSpeech = engine): String? = ReflectionHelpers.getField(tts, "mRequestedEngine")

    fun finishStarting(tts: TextToSpeech = engine, status: Int = TextToSpeech.SUCCESS) {
        shadowOf(tts).onInitListener.onInit(status)
    }

    fun spoken(tts: TextToSpeech = engine): List<String> = shadowOf(tts).spokenTextList
}
