package io.bemylens.app.integration

import android.net.FakeUri
import android.net.Uri
import io.bemylens.app.integration.ExternalIntegrationContract.Extras
import io.bemylens.app.integration.ExternalIntegrationContract.Modes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The launches the shipped Jieshuo plugins (dist/jieshuo-lua) make, parsed by the app.
 *
 * The Lua side of each payload is verified by running the real scripts in
 * tests/jieshuo; this is the Android side of the same hand-off. Screenshot plugins offer
 * one URI through EXTRA_STREAM, the custom IMAGE_URI extra and Intent.data at once.
 */
class JieshuoPluginCommandsTest {
    private val screenshotUri: Uri = FakeUri("content://com.nirenr.talkman.fileprovider/be_my_lens_1700000000001.png")

    private fun screenshotLaunch(vararg extras: Pair<String, String>) = FakeCommandSource(
        streamUri = screenshotUri,
        customImageUri = screenshotUri,
        dataUri = screenshotUri,
        stringExtras = mapOf(*extras),
    )

    @Test
    fun describePictureDescribesTheScreenshotAndSpeaks() {
        val command = ExternalImageIntentParser.parse(screenshotLaunch(Extras.MODE to Modes.DESCRIBE_SCREEN))

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
        assertSame(screenshotUri, command.imageUri)
        assertNull(command.prompt)
        assertTrue(command.autoSpeak)
    }

    @Test
    fun readPictureTextReadsTheScreenshot() {
        val command = ExternalImageIntentParser.parse(screenshotLaunch(Extras.MODE to Modes.READ_TEXT))

        assertEquals(Modes.READ_TEXT, command.mode)
        assertSame(screenshotUri, command.imageUri)
    }

    @Test
    fun translatePictureAsksItsTranslationPromptAboutTheScreenshot() {
        val prompt = "ترجم النص الظاهر في هذه الصورة إلى العربية."

        val command = ExternalImageIntentParser.parse(
            screenshotLaunch(Extras.MODE to Modes.CUSTOM_PROMPT, Extras.PROMPT to prompt),
        )

        assertEquals(Modes.CUSTOM_PROMPT, command.mode)
        assertEquals(prompt, command.prompt)
        assertSame(screenshotUri, command.imageUri)
    }

    @Test
    fun translateTextTranslatesTheFocusedTextWithoutAnImage() {
        val command = ExternalImageIntentParser.parse(
            FakeCommandSource(
                stringExtras = mapOf(
                    Extras.MODE to Modes.TRANSLATE_TEXT,
                    Extras.TEXT to "  Exit 12A is 300 meters ahead\n",
                ),
                booleanExtras = mapOf(Extras.AUTO_SPEAK to true),
            ),
        )

        assertEquals(Modes.TRANSLATE_TEXT, command.mode)
        assertEquals("Exit 12A is 300 meters ahead", command.text)
        assertNull(command.imageUri)
        assertTrue(command.autoSpeak)
    }
}
