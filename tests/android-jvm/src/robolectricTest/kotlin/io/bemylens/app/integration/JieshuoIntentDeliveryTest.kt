package io.bemylens.app.integration

import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Parcel
import io.bemylens.app.integration.ExternalIntegrationContract.ACTION_DESCRIBE_IMAGE
import io.bemylens.app.integration.ExternalIntegrationContract.Extras
import io.bemylens.app.integration.ExternalIntegrationContract.Modes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Real Android Intents, built the way the Jieshuo plugins and the documented adb commands
 * build them, delivered across a process boundary (Parcel round trip) and parsed by
 * [ExternalImageIntentParser.parse] through its Android adapter.
 *
 * Runs on minSdk (26) and targetSdk (35) to cover both branches of the adapter's
 * getParcelableExtra calls (before and after Android 13).
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 35])
class JieshuoIntentDeliveryTest {
    private val screenshot = Uri.parse("content://com.nirenr.talkman.fileprovider/be_my_lens_describe_screen_1.png")

    /** What the screenshot plugins in dist/jieshuo-lua build (see launchBeMyLens in those scripts). */
    private fun screenshotPluginIntent(mode: String, prompt: String? = null): Intent {
        val intent = Intent()
            .setAction(ACTION_DESCRIBE_IMAGE)
            .setComponent(ComponentName("io.bemylens.app", "io.bemylens.app.JieshuoEntryActivity"))
            .setPackage("io.bemylens.app")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            .putExtra(Extras.MODE, mode)
        prompt?.let { intent.putExtra(Extras.PROMPT, it) }
        intent.setDataAndType(screenshot, "image/png")
        intent.putExtra(Intent.EXTRA_STREAM, screenshot)
        intent.putExtra(Extras.IMAGE_URI, screenshot)
        return intent
    }

    /** Android parcels every Intent sent to another app; extras must survive that. */
    private fun Intent.deliveredToBeMyLens(): Intent {
        val parcel = Parcel.obtain()
        try {
            writeToParcel(parcel, 0)
            parcel.setDataPosition(0)
            return Intent.CREATOR.createFromParcel(parcel)
        } finally {
            parcel.recycle()
        }
    }

    private fun parse(intent: Intent) = ExternalImageIntentParser.parse(intent.deliveredToBeMyLens())

    @Test
    fun describePicturePluginLaunch() {
        val command = parse(screenshotPluginIntent(Modes.DESCRIBE_SCREEN))

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
        assertEquals(screenshot, command.imageUri)
        assertNull(command.prompt)
        assertTrue(command.autoSpeak)
    }

    @Test
    fun translatePicturePluginLaunchKeepsItsPrompt() {
        val prompt = "ترجم النص الظاهر في هذه الصورة إلى العربية."

        val command = parse(screenshotPluginIntent(Modes.CUSTOM_PROMPT, prompt))

        assertEquals(Modes.CUSTOM_PROMPT, command.mode)
        assertEquals(prompt, command.prompt)
        assertEquals(screenshot, command.imageUri)
    }

    @Test
    fun translateTextPluginLaunch() {
        val intent = Intent()
            .setAction(ACTION_DESCRIBE_IMAGE)
            .setComponent(ComponentName("io.bemylens.app", "io.bemylens.app.JieshuoEntryActivity"))
            .putExtra(Extras.MODE, Modes.TRANSLATE_TEXT)
            .putExtra(Extras.AUTO_SPEAK, true)
            .putExtra(Extras.TEXT, "Exit 12A is 300 meters ahead")

        val command = parse(intent)

        assertEquals(Modes.TRANSLATE_TEXT, command.mode)
        assertEquals("Exit 12A is 300 meters ahead", command.text)
        assertNull(command.imageUri)
    }

    @Test
    fun androidShareSheetSendsOnlyTheStreamExtra() {
        val intent = Intent(Intent.ACTION_SEND).setType("image/jpeg").putExtra(Intent.EXTRA_STREAM, screenshot)

        val command = parse(intent)

        assertEquals(Modes.DESCRIBE_SCREEN, command.mode)
        assertEquals(screenshot, command.imageUri)
    }

    @Test
    fun imageUriPassedAsAStringExtraIsAccepted() {
        // adb shell am start ... --es io.bemylens.app.extra.IMAGE_URI "content://..."
        val intent = Intent(ACTION_DESCRIBE_IMAGE).putExtra(Extras.IMAGE_URI, screenshot.toString())

        val command = parse(intent)

        assertEquals(screenshot, command.imageUri)
    }

    @Test
    fun imageUriInIntentDataIsAccepted() {
        // adb shell am start -a io.bemylens.app.action.DESCRIBE_IMAGE -d "content://..."
        val intent = Intent(ACTION_DESCRIBE_IMAGE).setData(screenshot)

        val command = parse(intent)

        assertEquals(screenshot, command.imageUri)
    }

    @Test
    fun streamExtraWinsOverOtherImageSources() {
        val other = Uri.parse("content://elsewhere/image/9")
        val intent = Intent(ACTION_DESCRIBE_IMAGE)
            .setData(other)
            .putExtra(Extras.IMAGE_URI, other)
            .putExtra(Intent.EXTRA_STREAM, screenshot)

        val command = parse(intent)

        assertEquals(screenshot, command.imageUri)
    }

    @Test
    fun autoSpeakCanBeTurnedOff() {
        val intent = screenshotPluginIntent(Modes.READ_TEXT).putExtra(Extras.AUTO_SPEAK, false)

        val command = parse(intent)

        assertFalse(command.autoSpeak)
    }

    @Test
    fun launchWithoutAnImageIsRejected() {
        // The no-image smoke test from prototypes/jieshuo/describe_image.lua.
        val intent = Intent(ACTION_DESCRIBE_IMAGE).putExtra(Extras.MODE, Modes.DESCRIBE_SCREEN)

        val error = assertThrows(ExternalImageCommandException::class.java) { parse(intent) }

        assertEquals(ExternalImageCommandError.NO_IMAGE_RECEIVED, error.error)
    }
}
