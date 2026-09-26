package io.bemylens.app.tts

import java.util.Locale

/**
 * Engine and voice filtering plus the rules for turning a saved selection into the one
 * that can actually be applied. Deliberately free of Android APIs so the Arabic filtering
 * and the fallback behaviour can be unit tested.
 */
object TtsCatalog {
    const val ARABIC_LANGUAGE = "ar"

    /** Some engines report the Arabic ISO code as the legacy `arb` tag. */
    private const val ARABIC_LEGACY_LANGUAGE = "arb"

    fun orderedEngines(engines: List<TtsEngineOption>): List<TtsEngineOption> {
        return engines
            .distinctBy { it.componentName }
            .sortedWith(compareBy({ it.label.lowercase(Locale.ROOT) }, { it.packageName }))
    }

    fun arabicVoices(voices: List<TtsVoiceOption>): List<TtsVoiceOption> {
        return voices
            .filter { isArabic(it.languageTag) }
            .distinctBy { it.voiceId }
            .sortedWith(compareBy({ it.languageTag }, { it.name }))
    }

    /** Keeps the saved engine only while it is still installed, otherwise falls back to the system default. */
    fun resolveEngineComponent(available: List<TtsEngineOption>, saved: String?): String? {
        val candidate = normalizeStoredValue(saved) ?: return null
        return candidate.takeIf { savedEngine -> available.any { it.componentName == savedEngine } }
    }

    /** Keeps the saved voice only while the active engine still offers it, otherwise the engine default is used. */
    fun resolveVoiceId(available: List<TtsVoiceOption>, saved: String?): String? {
        val candidate = normalizeStoredValue(saved) ?: return null
        return candidate.takeIf { savedVoice -> available.any { it.voiceId == savedVoice } }
    }

    /** Treats a missing or blank stored value as "nothing selected". */
    fun normalizeStoredValue(value: String?): String? {
        return value?.trim()?.takeIf { it.isNotEmpty() }
    }

    fun isArabic(languageTag: String): Boolean {
        val language = languageTag.lowercase(Locale.ROOT)
            .substringBefore('-')
            .substringBefore('_')
        return language == ARABIC_LANGUAGE || language == ARABIC_LEGACY_LANGUAGE
    }
}
