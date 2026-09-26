package io.bemylens.app.tts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TtsCatalogTest {
    @Test
    fun arabicVoicesKeepRegionalVariants() {
        val voices = listOf(
            voice("name:ar-SA", "ar-SA"),
            voice("name:ar-EG", "ar-EG"),
        )

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(listOf("name:ar-EG", "name:ar-SA"), result.map { it.voiceId })
    }

    @Test
    fun arabicVoicesDropOtherLanguages() {
        val voices = listOf(
            voice("english:en-US", "en-US"),
            voice("french:fr-FR", "fr-FR"),
        )

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(emptyList<TtsVoiceOption>(), result)
    }

    @Test
    fun arabicVoicesKeepLegacyArabicLanguageTag() {
        val voices = listOf(voice("msa:arb", "arb"))

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(listOf("msa:arb"), result.map { it.voiceId })
    }

    @Test
    fun arabicVoicesDoNotMatchLanguagesThatMerelyStartWithAr() {
        val voices = listOf(voice("aramaic:arc", "arc"))

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(emptyList<TtsVoiceOption>(), result)
    }

    @Test
    fun arabicVoicesDropDuplicatesFromEngine() {
        val voices = listOf(
            voice("name:ar-SA", "ar-SA"),
            voice("name:ar-SA", "ar-SA"),
        )

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(1, result.size)
    }

    @Test
    fun arabicVoicesSortByLanguageTagThenName() {
        val voices = listOf(
            voice("zulu:ar-SA", "ar-SA"),
            voice("alpha:ar-SA", "ar-SA"),
            voice("other:ar-EG", "ar-EG"),
        )

        val result = TtsCatalog.arabicVoices(voices)

        assertEquals(
            listOf("other:ar-EG", "alpha:ar-SA", "zulu:ar-SA"),
            result.map { it.voiceId },
        )
    }

    @Test
    fun resolveEngineComponentKeepsInstalledEngine() {
        val engines = listOf(engine("com.example.tts/com.example.tts.Engine"))

        val result = TtsCatalog.resolveEngineComponent(engines, "com.example.tts/com.example.tts.Engine")

        assertEquals("com.example.tts/com.example.tts.Engine", result)
    }

    @Test
    fun resolveEngineComponentFallsBackToSystemDefaultWhenEngineIsUninstalled() {
        val engines = listOf(engine("com.example.tts/com.example.tts.Engine"))

        val result = TtsCatalog.resolveEngineComponent(engines, "com.removed.tts/com.removed.tts.Engine")

        assertNull(result)
    }

    @Test
    fun resolveEngineComponentTreatsNothingSavedAsSystemDefault() {
        val engines = listOf(engine("com.example.tts/com.example.tts.Engine"))

        assertNull(TtsCatalog.resolveEngineComponent(engines, null))
        assertNull(TtsCatalog.resolveEngineComponent(engines, "  "))
    }

    @Test
    fun resolveVoiceIdKeepsVoiceTheEngineStillOffers() {
        val voices = listOf(voice("name:ar-SA", "ar-SA"))

        val result = TtsCatalog.resolveVoiceId(voices, "name:ar-SA")

        assertEquals("name:ar-SA", result)
    }

    @Test
    fun resolveVoiceIdFallsBackToEngineDefaultWhenVoiceIsGone() {
        val voices = listOf(voice("name:ar-SA", "ar-SA"))

        val result = TtsCatalog.resolveVoiceId(voices, "name:ar-EG")

        assertNull(result)
    }

    @Test
    fun resolveVoiceIdIgnoresVoicesFromAnotherEngine() {
        val voices = listOf(voice("name:ar-SA", "ar-SA"))

        val result = TtsCatalog.resolveVoiceId(voices, "other-name:ar-SA")

        assertNull(result)
    }

    @Test
    fun orderedEnginesSortByLabelAndDropDuplicateServices() {
        val engines = listOf(
            engine("com.z/com.z.Engine", label = "Zebra TTS"),
            engine("com.a/com.a.Engine", label = "Apple TTS"),
            engine("com.a/com.a.Engine", label = "Apple TTS"),
        )

        val result = TtsCatalog.orderedEngines(engines)

        assertEquals(listOf("Apple TTS", "Zebra TTS"), result.map { it.label })
    }

    @Test
    fun normalizeStoredValueTreatsBlankStoredValuesAsUnset() {
        assertNull(TtsCatalog.normalizeStoredValue(null))
        assertNull(TtsCatalog.normalizeStoredValue(""))
        assertNull(TtsCatalog.normalizeStoredValue("   "))
        assertEquals("name:ar-SA", TtsCatalog.normalizeStoredValue(" name:ar-SA "))
    }

    private fun engine(component: String, label: String = label(component)): TtsEngineOption {
        return TtsEngineOption(
            componentName = component,
            packageName = component.substringBefore('/'),
            label = label,
        )
    }

    private fun voice(voiceId: String, languageTag: String): TtsVoiceOption {
        return TtsVoiceOption(
            voiceId = voiceId,
            name = voiceId.substringBefore(':'),
            languageTag = languageTag,
        )
    }

    private fun label(component: String): String {
        return component.substringAfter('.').substringBefore('/')
    }
}
