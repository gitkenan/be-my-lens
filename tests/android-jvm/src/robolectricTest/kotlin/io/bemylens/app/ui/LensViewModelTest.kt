package io.bemylens.app.ui

import android.net.Uri
import android.os.Looper
import io.bemylens.app.BuildConfig
import io.bemylens.app.ChatMessage
import io.bemylens.app.ChatRole
import io.bemylens.app.R
import io.bemylens.app.testing.AppStrings
import io.bemylens.app.testing.AppStringsApplication
import io.bemylens.app.testing.FakeBackend
import io.bemylens.app.testing.TestImages
import io.bemylens.app.testing.endpoint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/**
 * The main screen's state machine: the real LensViewModel, its real LensRepository and
 * image pipeline, talking to a fake backend, with the app's real string resources.
 *
 * The harness's BuildConfig is a debug build, so error messages include the debug detail
 * (build marker and exception). Release builds show only the short message, which these
 * tests cannot exercise.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], application = AppStringsApplication::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class LensViewModelTest {
    @get:Rule
    val backend = FakeBackend()

    private val application = RuntimeEnvironment.getApplication()
    private val viewModel = LensViewModel(application)

    private fun photo(): Uri {
        val file = TestImages.writePng(File(application.cacheDir, "gallery/photo.png"), 1200, 900)
        val uri = Uri.parse("content://media/external/images/media/7")
        shadowOf(application.contentResolver).registerInputStreamSupplier(uri) { file.inputStream() }
        return uri
    }

    /** Runs main-thread work (viewModelScope) until the current request has finished. */
    private fun awaitIdle() {
        val deadline = System.currentTimeMillis() + 10_000
        do {
            shadowOf(Looper.getMainLooper()).idle()
            if (!viewModel.uiState.value.isLoading) return
            Thread.sleep(10)
        } while (System.currentTimeMillis() < deadline)
        throw AssertionError("request did not finish: ${viewModel.uiState.value}")
    }

    private fun describedPhoto(description: String = "باب أحمر.") {
        viewModel.onImageSelected(photo())
        backend.respondJson("""{"sessionId": "session-1", "description": "$description"}""")
        viewModel.describeSelectedImage()
        awaitIdle()
        backend.takeRequest()
    }

    private val state get() = viewModel.uiState.value

    @Test
    fun describingAPhotoShowsTheDescriptionAndStartsAConversation() {
        viewModel.onImageSelected(photo())
        backend.respondJson("""{"sessionId": "session-1", "description": "باب أحمر عليه لافتة خروج."}""")

        viewModel.describeSelectedImage()
        assertTrue("shows progress while waiting", state.isLoading)
        awaitIdle()

        assertEquals("/describe", backend.takeRequest().endpoint)
        assertEquals("باب أحمر عليه لافتة خروج.", state.latestAnswer)
        assertEquals("session-1", state.sessionId)
        assertEquals(listOf(ChatMessage(ChatRole.ASSISTANT, "باب أحمر عليه لافتة خروج.")), state.messages)
        assertNull(state.errorMessage)
    }

    @Test
    fun readingAPhotoShowsItsText() {
        viewModel.onImageSelected(photo())
        backend.respondJson("""{"sessionId": "session-2", "contents": "Exit 12A"}""")

        viewModel.readSelectedImage()
        awaitIdle()

        assertEquals("/read", backend.takeRequest().endpoint)
        assertEquals("Exit 12A", state.latestAnswer)
        assertEquals("session-2", state.sessionId)
    }

    @Test
    fun followUpContinuesTheSameSession() {
        describedPhoto()
        viewModel.openChat()
        viewModel.updateFollowUpQuestion("  Is the door open?  ")
        backend.respondJson("""{"answer": "It is closed."}""")

        viewModel.sendFollowUp()
        awaitIdle()

        val request = backend.takeRequest()
        assertEquals("/followup", request.endpoint)
        assertEquals("""{"sessionId":"session-1","question":"Is the door open?"}""", request.body.readUtf8())
        assertEquals(
            listOf(
                ChatMessage(ChatRole.ASSISTANT, "باب أحمر."),
                ChatMessage(ChatRole.USER, "Is the door open?"),
                ChatMessage(ChatRole.ASSISTANT, "It is closed."),
            ),
            state.messages,
        )
        assertEquals("It is closed.", state.latestAnswer)
        assertEquals("", state.followUpQuestion)
        assertTrue(state.isChatOpen)
    }

    @Test
    fun askingBeforeDescribingUploadsThePhotoWithTheQuestionThenFollowsUpInThatSession() {
        viewModel.onImageSelected(photo())
        viewModel.openChat()
        backend.respondJson("""{"sessionId": "session-chat", "answer": "A kettle."}""")
        viewModel.sendShortcut("ما الأشياء الموجودة هنا؟")
        awaitIdle()
        backend.respondJson("""{"answer": "It is silver."}""")

        viewModel.sendFollowUp("What colour is it?")
        awaitIdle()

        assertEquals("/chat", backend.takeRequest().endpoint)
        val followUp = backend.takeRequest()
        assertEquals("/followup", followUp.endpoint)
        assertTrue(followUp.body.readUtf8().contains("\"sessionId\":\"session-chat\""))
        assertEquals("It is silver.", state.latestAnswer)
    }

    @Test
    fun failedFollowUpWithdrawsTheQuestionAndExplainsTheError() {
        describedPhoto()
        backend.respondJson("""{"detail": "upstream"}""", status = 502)

        viewModel.sendFollowUp("Is the door open?")
        awaitIdle()

        assertEquals(listOf(ChatMessage(ChatRole.ASSISTANT, "باب أحمر.")), state.messages)
        assertEquals("باب أحمر.", state.latestAnswer)
        val error = state.errorMessage!!
        assertTrue(error, error.startsWith(AppStrings.get(R.string.debug_error_build).format(BuildConfig.BUILD_MARKER)))
        assertTrue(error, error.contains("retrofit2.HttpException"))
        assertFalse(state.isLoading)
    }

    @Test
    fun failedDescriptionLeavesNoAnswerAndExplainsTheError() {
        viewModel.onImageSelected(photo())
        backend.respondJson("""{"detail": "upstream"}""", status = 502)

        viewModel.describeSelectedImage()
        awaitIdle()

        assertNull(state.latestAnswer)
        assertNull(state.sessionId)
        assertTrue(state.errorMessage!!.contains("HTTP 502"))
    }

    @Test
    fun blankQuestionsAreNotSent() {
        describedPhoto()

        viewModel.sendFollowUp("   ")
        shadowOf(Looper.getMainLooper()).idle()

        assertEquals("only the description was requested", 1, backend.requestCount)
        assertEquals(1, state.messages.size)
    }

    @Test
    fun choosingANewPhotoStartsOver() {
        describedPhoto()

        viewModel.onImageSelected(photo())

        assertNull(state.latestAnswer)
        assertNull(state.sessionId)
        assertEquals(emptyList<ChatMessage>(), state.messages)
    }
}
