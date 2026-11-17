package io.bemylens.app.data

import android.net.Uri
import io.bemylens.app.testing.FakeBackend
import io.bemylens.app.testing.TestImages
import io.bemylens.app.testing.endpoint
import io.bemylens.app.testing.multipartFields
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import retrofit2.HttpException
import java.io.File
import java.io.InputStream

/**
 * The app's real data layer: LensRepository, its OkHttp/Retrofit client, and the image
 * pipeline in ImageUtils decoding real images with Android's native graphics code.
 *
 * JSON endpoints run on minSdk (26) and targetSdk (35). Image tests run on 35 only:
 * Robolectric's native graphics start at API 28, and older levels get fake 100x100 bitmaps.
 * Images come from a `content://` URI, as the photo picker supplies them. Robolectric
 * cannot decode from a file descriptor, which is how Jieshuo's copied `file://` images
 * are opened. The decode, scale and JPEG steps after that are the same code.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 35])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class LensRepositoryTest {
    @get:Rule
    val backend = FakeBackend()

    private val context = RuntimeEnvironment.getApplication()
    private val repository = LensRepository(context)
    private var nextImageId = 1

    /** A gallery image, served by the content resolver like a photo-picker result. */
    private fun galleryImage(width: Int, height: Int): Uri {
        val file = TestImages.writePng(File(context.cacheDir, "gallery/${width}x$height.png"), width, height)
        return galleryUri { file.inputStream() }
    }

    private fun galleryUri(open: () -> InputStream): Uri {
        val uri = Uri.parse("content://media/external/images/media/${nextImageId++}")
        shadowOf(context.contentResolver).registerInputStreamSupplier(uri, open)
        return uri
    }

    @Test
    @Config(sdk = [35])
    fun describeUploadsALargePhotoAsJpegScaledToAtMost1600Pixels() = runBlocking {
        backend.respondJson("""{"sessionId": "s-1", "description": "باب أحمر."}""")

        val response = repository.describeImage(galleryImage(width = 4000, height = 3000))

        val request = backend.takeRequest()
        assertEquals("/describe", request.endpoint)
        val image = request.multipartFields().getValue("image")
        assertEquals("image.jpg", image.filename)
        assertEquals("image/jpeg", image.contentType)
        assertEquals(TestImages.Decoded("jpeg", 1600, 1200), TestImages.decode(image.body))
        assertEquals(DescribeResponse(sessionId = "s-1", description = "باب أحمر."), response)
    }

    @Test
    @Config(sdk = [35])
    fun tallImagesAreScaledByTheirLongestSide() = runBlocking {
        backend.respondJson("""{"sessionId": "s-2", "contents": "Exit 12A"}""")

        repository.readContents(galleryImage(width = 1000, height = 3200))

        val request = backend.takeRequest()
        assertEquals("/read", request.endpoint)
        assertEquals(TestImages.Decoded("jpeg", 500, 1600), TestImages.decode(request.multipartFields().getValue("image").body))
    }

    @Test
    @Config(sdk = [35])
    fun smallImagesAreNotUpscaled() = runBlocking {
        backend.respondJson("""{"sessionId": "s-3", "answer": "A kettle."}""")

        repository.askQuestion(galleryImage(width = 640, height = 480), "ما هذا؟")

        val fields = backend.takeRequest().multipartFields()
        assertEquals(TestImages.Decoded("jpeg", 640, 480), TestImages.decode(fields.getValue("image").body))
        assertEquals("ما هذا؟", fields.getValue("question").text)
    }

    @Test
    fun followUpAndTranslateSendJsonToTheBackend() = runBlocking {
        backend.respondJson("""{"answer": "It is closed."}""")
        backend.respondJson("""{"answer": "مرحبا"}""")

        val followUp = repository.followUp(sessionId = "s-1", question = "Is the door open?")
        val translation = repository.translateText("hello")

        val followUpRequest = backend.takeRequest()
        assertEquals("/followup", followUpRequest.endpoint)
        assertEquals("""{"sessionId":"s-1","question":"Is the door open?"}""", followUpRequest.body.readUtf8())
        val translateRequest = backend.takeRequest()
        assertEquals("/translate_text", translateRequest.endpoint)
        assertEquals("""{"text":"hello"}""", translateRequest.body.readUtf8())
        assertEquals("It is closed.", followUp.answer)
        assertEquals("مرحبا", translation.answer)
    }

    @Test
    fun backendFailureReachesTheCallerAsAnHttpError() {
        backend.respondJson("""{"detail": "تعذر الاتصال بخدمة الذكاء الاصطناعي. حاول مرة أخرى."}""", status = 502)

        val error = assertThrows(HttpException::class.java) {
            runBlocking { repository.translateText("hello") }
        }

        assertEquals(502, error.code())
    }

    @Test
    @Config(sdk = [35])
    fun aFileThatIsNotAnImageFailsBeforeAnythingIsUploaded() {
        val notAnImage = galleryUri { "this is not an image".byteInputStream() }

        val error = runCatching { runBlocking { repository.describeImage(notAnImage) } }.exceptionOrNull()

        assertTrue("decoding garbage must fail", error != null)
        assertEquals(0, backend.requestCount)
    }
}
