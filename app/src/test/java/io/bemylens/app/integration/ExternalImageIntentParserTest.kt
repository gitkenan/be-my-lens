package io.bemylens.app.integration

import android.net.FakeUri
import android.net.Uri
import io.bemylens.app.integration.ExternalImageCommandError.CUSTOM_PROMPT_REQUIRED
import io.bemylens.app.integration.ExternalImageCommandError.NO_IMAGE_RECEIVED
import io.bemylens.app.integration.ExternalImageCommandError.NO_TEXT_RECEIVED
import io.bemylens.app.integration.ExternalImageCommandError.UNSUPPORTED_MODE
import io.bemylens.app.integration.ExternalIntegrationContract.Extras
import io.bemylens.app.integration.ExternalIntegrationContract.Modes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class ExternalImageIntentParserTest {
    private val imageUri: Uri = FakeUri("content://example.images/image/1")

    @Test
    fun parsesActionSendWithExtraStream() {
        val source = FakeCommandSource(streamUri = imageUri)

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
        assertSame(imageUri, command.imageUri)
    }

    @Test
    fun parsesCustomActionWithCustomImageUriExtra() {
        val source = FakeCommandSource(
            customImageUri = imageUri,
            stringExtras = mapOf(Extras.MODE to Modes.FOCUSED_ITEM),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.FOCUSED_ITEM, command.mode)
        assertSame(imageUri, command.imageUri)
    }

    @Test
    fun parsesCustomActionWithDataUri() {
        val source = FakeCommandSource(dataUri = imageUri)

        val command = ExternalImageIntentParser.parse(source)

        assertSame(imageUri, command.imageUri)
    }

    @Test
    fun missingImageThrowsClearError() {
        val source = FakeCommandSource()

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(NO_IMAGE_RECEIVED, error.error)
    }

    @Test
    fun missingModeDefaultsToDescribeScreen() {
        val source = FakeCommandSource(customImageUri = imageUri)

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
    }

    @Test
    fun autoSpeakDefaultsToTrue() {
        val source = FakeCommandSource(customImageUri = imageUri)

        val command = ExternalImageIntentParser.parse(source)

        assertTrue(command.autoSpeak)
    }

    @Test
    fun unsupportedModeThrowsClearError() {
        val source = FakeCommandSource(
            customImageUri = imageUri,
            stringExtras = mapOf(Extras.MODE to "unknown_mode"),
        )

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(UNSUPPORTED_MODE, error.error)
        assertEquals("unknown_mode", error.value)
    }

    @Test
    fun customPromptWithoutPromptThrowsClearError() {
        val source = FakeCommandSource(
            customImageUri = imageUri,
            stringExtras = mapOf(Extras.MODE to Modes.CUSTOM_PROMPT),
        )

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(CUSTOM_PROMPT_REQUIRED, error.error)
    }

    @Test
    fun parsesTranslateTextWithoutImage() {
        val source = FakeCommandSource(
            stringExtras = mapOf(
                Extras.MODE to Modes.TRANSLATE_TEXT,
                Extras.TEXT to "  hello  ",
            ),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.TRANSLATE_TEXT, command.mode)
        assertEquals("hello", command.text)
        assertEquals(null, command.imageUri)
    }

    @Test
    fun translateTextWithoutTextThrowsClearError() {
        val source = FakeCommandSource(
            stringExtras = mapOf(Extras.MODE to Modes.TRANSLATE_TEXT),
        )

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(NO_TEXT_RECEIVED, error.error)
    }

    @Test
    fun translateTextWithWhitespaceTextThrowsClearError() {
        val source = FakeCommandSource(
            stringExtras = mapOf(
                Extras.MODE to Modes.TRANSLATE_TEXT,
                Extras.TEXT to "   ",
            ),
        )

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(NO_TEXT_RECEIVED, error.error)
    }

    @Test
    fun streamUriTakesPrecedenceOverOtherImageSources() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            customImageUri = otherUri,
            dataUri = thirdUri,
        )

        val command = ExternalImageIntentParser.parse(source)

        assertSame(imageUri, command.imageUri)
    }

    @Test
    fun customImageUriTakesPrecedenceOverIntentData() {
        val source = FakeCommandSource(customImageUri = imageUri, dataUri = otherUri)

        val command = ExternalImageIntentParser.parse(source)

        assertSame(imageUri, command.imageUri)
    }

    @Test
    fun autoSpeakCanBeTurnedOff() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            booleanExtras = mapOf(Extras.AUTO_SPEAK to false),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertFalse(command.autoSpeak)
    }

    @Test
    fun modeAndPromptAreTrimmed() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            stringExtras = mapOf(
                Extras.MODE to "  ${Modes.READ_TEXT}\n",
                Extras.PROMPT to "  Read only the price.  ",
            ),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.READ_TEXT, command.mode)
        assertEquals("Read only the price.", command.prompt)
    }

    @Test
    fun blankModeFallsBackToDescribeScreen() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            stringExtras = mapOf(Extras.MODE to "   "),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
    }

    @Test
    fun blankPromptIsTreatedAsNoPrompt() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            stringExtras = mapOf(Extras.PROMPT to "  "),
        )

        val command = ExternalImageIntentParser.parse(source)

        assertNull(command.prompt)
    }

    @Test
    fun customPromptWithBlankPromptThrowsClearError() {
        val source = FakeCommandSource(
            streamUri = imageUri,
            stringExtras = mapOf(Extras.MODE to Modes.CUSTOM_PROMPT, Extras.PROMPT to "   "),
        )

        val error = assertThrows(ExternalImageCommandException::class.java) {
            ExternalImageIntentParser.parse(source)
        }

        assertEquals(CUSTOM_PROMPT_REQUIRED, error.error)
    }

    @Test
    fun everyImageModeRequiresAnImage() {
        val imageModes = Modes.SUPPORTED - Modes.TRANSLATE_TEXT

        for (mode in imageModes) {
            val source = FakeCommandSource(
                stringExtras = mapOf(Extras.MODE to mode, Extras.PROMPT to "Describe it."),
            )

            val error = assertThrows(mode, ExternalImageCommandException::class.java) {
                ExternalImageIntentParser.parse(source)
            }

            assertEquals(mode, NO_IMAGE_RECEIVED, error.error)
        }
    }

    private companion object {
        val otherUri: Uri = FakeUri("content://example.images/image/2")
        val thirdUri: Uri = FakeUri("file:///sdcard/BeMyLens/image3.png")
    }
}
