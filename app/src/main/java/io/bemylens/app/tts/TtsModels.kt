package io.bemylens.app.tts

/**
 * A text-to-speech engine installed on the device, discovered through
 * [android.speech.tts.TextToSpeech.Engine.ACTION_TTS_SERVICE].
 */
data class TtsEngineOption(
    /** Flattened service component handed to the `TextToSpeech` engine constructor. */
    val componentName: String,
    /** Package the engine lives in, kept for display and for grouping per app. */
    val packageName: String,
    /** Human readable engine name shown in settings. */
    val label: String,
)

/** A single voice offered by the active engine. */
data class TtsVoiceOption(
    /** Engine scoped identifier passed to `setVoice()` and persisted as-is. */
    val voiceId: String,
    /** Raw engine voice name, e.g. `ar-x-iaa-local`. */
    val name: String,
    /** BCP 47 tag of the voice locale, e.g. `ar-SA`. */
    val languageTag: String,
)

/**
 * The user's saved choice. `null` always means "let the system or the engine decide",
 * which is what a fresh install uses.
 */
data class TtsSelection(
    val engineComponent: String? = null,
    val voiceId: String? = null,
)

/** State the settings screen renders. */
data class TtsSettingsState(
    /** False until the engine reported back, then true whether it started or not. */
    val isInitialised: Boolean = false,
    /** True only when speech will actually work. */
    val isReady: Boolean = false,
    val engines: List<TtsEngineOption> = emptyList(),
    val engineComponent: String? = null,
    val voices: List<TtsVoiceOption> = emptyList(),
    val voiceId: String? = null,
)
