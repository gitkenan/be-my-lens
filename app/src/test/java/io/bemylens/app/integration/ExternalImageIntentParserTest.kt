package io.bemylens.app.integration

import android.net.FakeUri
import android.net.Uri
import io.bemylens.app.integration.ExternalIntegrationContract.Extras
import io.bemylens.app.integration.ExternalIntegrationContract.Modes
import org.junit.Assert.assertEquals
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

        assertEquals("No image received.", error.message)
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

        assertTrue(error.message!!.contains("Unsupported mode: unknown_mode"))
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

        assertEquals("custom_prompt mode requires a prompt extra.", error.message)
    }

    private data class FakeCommandSource(
        override val streamUri: Uri? = null,
        override val customImageUri: Uri? = null,
        override val customImageUriString: String? = null,
        override val dataUri: Uri? = null,
        val stringExtras: Map<String, String> = emptyMap(),
        val booleanExtras: Map<String, Boolean> = emptyMap(),
    ) : ExternalImageCommandSource {
        override fun getStringExtra(key: String): String? {
            return stringExtras[key]
        }

        override fun getBooleanExtra(key: String, defaultValue: Boolean): Boolean {
            return booleanExtras[key] ?: defaultValue
        }
    }
}
