package io.bemylens.app.tts

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.Locale

/**
 * Process-wide wrapper around [TextToSpeech] that speaks with the engine and Arabic voice the
 * user picked in settings, so the main screen and the screen-reader entry point share one
 * engine. Must be created on the main thread; the platform connection is released when the
 * process ends.
 */
class TtsSpeaker private constructor(
    private val context: Context,
    private val settingsStore: TtsSettingsStore,
) {
    private val _state = MutableStateFlow(TtsSettingsState())
    val state: StateFlow<TtsSettingsState> = _state.asStateFlow()

    private val installedEngines: List<TtsEngineOption> = TtsEngines.installed(context)
    private var selection: TtsSelection = settingsStore.load()
    private var engine: TextToSpeech? = null
    private var engineVoices: List<Voice> = emptyList()
    private var activeEngineComponent: String? = null
    private var initFinished = false
    private var ready = false
    private var generation = 0
    private var pendingText: String? = null

    init {
        val restoredEngine = TtsCatalog.resolveEngineComponent(installedEngines, selection.engineComponent)
        if (restoredEngine == null && selection.engineComponent != null) {
            // Saved engine is gone, so start over from the system default.
            selection = selection.copy(engineComponent = null)
            settingsStore.save(selection)
        }
        createEngine(restoredEngine)
    }

    fun speak(text: String) {
        val tts = engine
        if (!ready || tts == null) {
            // Init can outrun the first read aloud button press, so hold the text back.
            pendingText = text
            return
        }
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, UTTERANCE_ID)
    }

    fun stop() {
        pendingText = null
        engine?.stop()
    }

    /** Pass `null` to hand control back to the system default engine. */
    fun selectEngine(component: String?) {
        val requested = TtsCatalog.normalizeStoredValue(component)
        val target = requested?.takeIf { value ->
            installedEngines.any { it.componentName == value }
        }
        if (target == activeEngineComponent) return

        // Voice IDs are only meaningful to the engine that created them.
        selection = selection.copy(engineComponent = target, voiceId = null)
        settingsStore.save(selection)
        activeEngineComponent = target
        createEngine(target)
    }

    /** Pass `null` to let the active engine pick its own Arabic voice. */
    fun selectVoice(voiceId: String?) {
        val target = TtsCatalog.normalizeStoredValue(voiceId)
        if (target == selection.voiceId) return

        selection = selection.copy(voiceId = target)
        settingsStore.save(selection)

        if (target == null) {
            // A voice set with setVoice() stays in effect for the life of the instance and
            // setLanguage() only clears voices of another language, so going back to the
            // engine default means starting the same engine again.
            createEngine(activeEngineComponent)
            return
        }

        val voice = engineVoices.firstOrNull { voiceIdOf(it) == target }
        if (ready && voice != null) {
            engine?.setVoice(voice)
        }
        publishState()
    }

    private fun createEngine(component: String?) {
        val currentGeneration = ++generation
        initFinished = false
        ready = false
        activeEngineComponent = component
        engineVoices = emptyList()
        engine?.stop()
        engine?.shutdown()
        engine = null

        val listener = TextToSpeech.OnInitListener { status ->
            if (currentGeneration == generation) {
                onEngineReady(component, status)
            }
        }
        // TextToSpeech's engine constructor argument is a package name, while our
        // persisted selection uses the service component so multiple services can be
        // distinguished reliably.
        val enginePackage = installedEngines
            .firstOrNull { it.componentName == component }
            ?.packageName
        engine = if (enginePackage == null) {
            TextToSpeech(context, listener)
        } else {
            TextToSpeech(context, listener, enginePackage)
        }
        publishState()
    }

    private fun onEngineReady(component: String?, status: Int) {
        initFinished = true
        val tts = engine
        if (status != TextToSpeech.SUCCESS || tts == null) {
            if (component != null) {
                Log.w(TAG, "TTS engine $component could not start, using the system default")
                selection = selection.copy(engineComponent = null)
                settingsStore.save(selection)
                activeEngineComponent = null
                createEngine(null)
            } else {
                Log.e(TAG, "No TTS engine could be started")
                publishState()
            }
            return
        }

        ready = true
        activeEngineComponent = component
        tts.setLanguage(ARABIC_LOCALE)
        engineVoices = runCatching { tts.voices }.getOrNull().orEmpty().toList()
        applyStoredVoice()
        publishState()
        speakPendingText()
    }

    private fun applyStoredVoice() {
        val tts = engine ?: return
        val voices = voiceOptions()
        val voiceId = TtsCatalog.resolveVoiceId(voices, selection.voiceId) ?: return
        engineVoices.firstOrNull { voiceIdOf(it) == voiceId }?.let(tts::setVoice)
    }

    private fun voiceOptions(): List<TtsVoiceOption> {
        return runCatching {
            TtsCatalog.arabicVoices(
                engineVoices.map { voice ->
                    TtsVoiceOption(
                        voiceId = voiceIdOf(voice),
                        name = voice.name,
                        languageTag = voice.locale.toLanguageTag(),
                    )
                },
            )
        }.getOrDefault(emptyList())
    }

    private fun publishState() {
        val voices = if (ready) voiceOptions() else emptyList()
        _state.value = TtsSettingsState(
            isInitialised = initFinished,
            isReady = ready,
            engines = installedEngines,
            engineComponent = activeEngineComponent,
            voices = voices,
            voiceId = TtsCatalog.resolveVoiceId(voices, selection.voiceId),
        )
    }

    private fun speakPendingText() {
        val text = pendingText ?: return
        pendingText = null
        speak(text)
    }

    /**
     * [Voice] exposes no public identifier, so the `name:locale` form is built here to
     * persist the choice and to find the same voice again after the engine restarts.
     */
    private fun voiceIdOf(voice: Voice): String {
        val locale = runCatching { voice.locale }.getOrNull()
        return "${voice.name}:${locale?.toLanguageTag().orEmpty()}"
    }

    companion object {
        private const val TAG = "BeMyLens"
        private const val UTTERANCE_ID = "be-my-lens"
        private val ARABIC_LOCALE = Locale("ar")

        @Volatile
        private var instance: TtsSpeaker? = null

        fun getInstance(context: Context): TtsSpeaker {
            return instance ?: synchronized(this) {
                instance ?: TtsSpeaker(
                    context.applicationContext,
                    SharedPreferencesTtsSettingsStore(context.applicationContext),
                ).also { instance = it }
            }
        }
    }
}
