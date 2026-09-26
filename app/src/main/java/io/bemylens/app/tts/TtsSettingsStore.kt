package io.bemylens.app.tts

import android.content.Context

/** Where the chosen engine and voice are kept between app launches. */
interface TtsSettingsStore {
    fun load(): TtsSelection

    fun save(selection: TtsSelection)
}

/**
 * Two keys in SharedPreferences, no database: the engine and the voice are stored
 * separately because voice ids only mean something to the engine that offered them.
 */
class SharedPreferencesTtsSettingsStore(context: Context) : TtsSettingsStore {
    private val preferences = context.applicationContext
        .getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    override fun load(): TtsSelection {
        return TtsSelection(
            engineComponent = TtsCatalog.normalizeStoredValue(preferences.getString(KEY_ENGINE, null)),
            voiceId = TtsCatalog.normalizeStoredValue(preferences.getString(KEY_VOICE, null)),
        )
    }

    override fun save(selection: TtsSelection) {
        // A null value removes the key, so "system default" leaves nothing behind.
        preferences.edit()
            .putString(KEY_ENGINE, selection.engineComponent)
            .putString(KEY_VOICE, selection.voiceId)
            .apply()
    }

    private companion object {
        const val PREFERENCES_NAME = "be-my-lens-tts"
        const val KEY_ENGINE = "tts_engine_component"
        const val KEY_VOICE = "tts_voice_id"
    }
}
