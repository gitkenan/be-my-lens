package io.bemylens.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import io.bemylens.app.data.LensRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.util.Locale

class JieshuoEntryActivity : ComponentActivity() {
    private val repository by lazy { LensRepository(applicationContext) }
    private var speaker: TextToSpeech? = null
    private var ttsReady = false
    private var pendingSpeech: String? = null
    private var processingJob: Job? = null
    private var latestRequestId = 0L
    private var screenState by mutableStateOf<JieshuoScreenState>(JieshuoScreenState.Processing)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        speaker = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                ttsReady = true
                speaker?.language = Locale.getDefault()
                pendingSpeech?.let { text ->
                    pendingSpeech = null
                    speak(text)
                }
            }
        }

        setContent {
            JieshuoEntryScreen(
                state = screenState,
                onSpeak = ::speak,
                onClose = ::finish,
            )
        }

        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    override fun onDestroy() {
        processingJob?.cancel()
        speaker?.stop()
        speaker?.shutdown()
        speaker = null
        super.onDestroy()
    }

    private fun handleIntent(intent: Intent) {
        processingJob?.cancel()
        pendingSpeech = null
        val requestId = ++latestRequestId
        screenState = JieshuoScreenState.Processing

        processingJob = lifecycleScope.launch {
            val result = runCatching {
                val request = intent.toJieshuoRequest()
                val cachedImageUri = withContext(Dispatchers.IO) {
                    copyImageToCache(request.imageUri)
                }

                val answer = if (request.prompt.isNullOrBlank()) {
                    repository.describeImage(cachedImageUri).description
                } else {
                    repository.askQuestion(cachedImageUri, request.prompt).answer
                }

                JieshuoScreenState.Result(
                    answer = answer,
                    mode = request.mode,
                    prompt = request.prompt,
                    autoSpeak = request.autoSpeak,
                )
            }.getOrElse { error ->
                if (error is CancellationException) {
                    return@launch
                }
                error.toJieshuoErrorState()
            }

            if (requestId != latestRequestId) {
                return@launch
            }

            screenState = result
            if (result is JieshuoScreenState.Result && result.autoSpeak) {
                speak(result.answer)
            }
        }
    }

    private fun Intent.toJieshuoRequest(): JieshuoRequest {
        val imageUri = receivedImageUri()
            ?: throw JieshuoInputException("No image received.")

        val type = type ?: contentResolver.getType(imageUri)
        if (type != null && !type.startsWith("image/")) {
            throw JieshuoInputException("Unsupported content type: $type")
        }

        return JieshuoRequest(
            imageUri = imageUri,
            mode = getStringExtra(EXTRA_MODE).orEmpty().ifBlank { DEFAULT_MODE },
            prompt = getStringExtra(EXTRA_PROMPT)?.trim()?.takeIf { it.isNotBlank() },
            autoSpeak = getBooleanExtra(EXTRA_AUTO_SPEAK, true),
        )
    }

    private fun Intent.receivedImageUri(): Uri? {
        return streamExtraUri()
            ?: customImageUriExtra()
            ?: data
    }

    private fun Intent.streamExtraUri(): Uri? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            getParcelableExtra(Intent.EXTRA_STREAM)
        }
    }

    private fun Intent.customImageUriExtra(): Uri? {
        val parcelableUri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getParcelableExtra(EXTRA_IMAGE_URI, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            getParcelableExtra(EXTRA_IMAGE_URI)
        }
        if (parcelableUri != null) return parcelableUri

        return getStringExtra(EXTRA_IMAGE_URI)?.let(Uri::parse)
    }

    private fun copyImageToCache(sourceUri: Uri): Uri {
        val scheme = sourceUri.scheme
        if (scheme != "content" && scheme != "file") {
            throw JieshuoInputException("Unsupported image URI: ${sourceUri.scheme ?: "none"}")
        }

        val incomingDir = File(cacheDir, "jieshuo").apply { mkdirs() }
        val imageFile = File.createTempFile("incoming_", ".jpg", incomingDir)

        try {
            contentResolver.openInputStream(sourceUri)?.use { input ->
                imageFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            } ?: throw JieshuoInputException("Unable to open received image.")
        } catch (error: SecurityException) {
            throw JieshuoInputException("Be My Lens does not have permission to read the received image.", error)
        } catch (error: IOException) {
            throw JieshuoInputException("Unable to copy the received image.", error)
        }

        return Uri.fromFile(imageFile)
    }

    private fun Throwable.toJieshuoErrorState(): JieshuoScreenState.Error {
        val message = when (this) {
            is JieshuoInputException -> message ?: "Unable to use the received image."
            else -> "Image decoding, upload, or backend processing failed."
        }

        return JieshuoScreenState.Error(
            message = message,
            detail = this.cause?.message ?: takeUnless { it is JieshuoInputException }?.message,
        )
    }

    private fun speak(text: String) {
        if (!ttsReady) {
            pendingSpeech = text
            return
        }

        speaker?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "be-my-lens-jieshuo")
    }

    companion object {
        const val ACTION_DESCRIBE_IMAGE = "io.bemylens.app.action.DESCRIBE_IMAGE"
        const val EXTRA_IMAGE_URI = "io.bemylens.app.extra.IMAGE_URI"
        const val EXTRA_MODE = "mode"
        const val EXTRA_PROMPT = "prompt"
        const val EXTRA_AUTO_SPEAK = "autoSpeak"
        const val DEFAULT_MODE = "describe_screen"
    }
}

private data class JieshuoRequest(
    val imageUri: Uri,
    val mode: String,
    val prompt: String?,
    val autoSpeak: Boolean,
)

private class JieshuoInputException(
    message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

private sealed interface JieshuoScreenState {
    data object Processing : JieshuoScreenState

    data class Result(
        val answer: String,
        val mode: String,
        val prompt: String?,
        val autoSpeak: Boolean,
    ) : JieshuoScreenState

    data class Error(
        val message: String,
        val detail: String?,
    ) : JieshuoScreenState
}

@Composable
private fun JieshuoEntryScreen(
    state: JieshuoScreenState,
    onSpeak: (String) -> Unit,
    onClose: () -> Unit,
) {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background)
                    .statusBarsPadding()
                    .padding(20.dp),
            ) {
                when (state) {
                    JieshuoScreenState.Processing -> ProcessingCard()
                    is JieshuoScreenState.Result -> ResultCard(
                        state = state,
                        onSpeak = onSpeak,
                        onClose = onClose,
                    )
                    is JieshuoScreenState.Error -> ErrorCard(
                        state = state,
                        onClose = onClose,
                    )
                }
            }
        }
    }
}

@Composable
private fun ProcessingCard() {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Text(
            text = "Describing image...",
            modifier = Modifier.padding(top = 18.dp),
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun ResultCard(
    state: JieshuoScreenState.Result,
    onSpeak: (String) -> Unit,
    onClose: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = "Be My Lens",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            shape = RoundedCornerShape(20.dp),
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    text = if (state.prompt == null) "Description" else "Answer",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = state.answer,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        Button(
            onClick = { onSpeak(state.answer) },
            modifier = Modifier.fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 14.dp),
        ) {
            Text("Read aloud")
        }
        OutlinedButton(
            onClick = onClose,
            modifier = Modifier.fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 14.dp),
        ) {
            Text("Close")
        }
    }
}

@Composable
private fun ErrorCard(
    state: JieshuoScreenState.Error,
    onClose: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
            shape = RoundedCornerShape(20.dp),
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(
                    text = "Unable to describe image",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = state.message,
                    style = MaterialTheme.typography.bodyLarge,
                )
                state.detail?.let { detail ->
                    Text(
                        text = detail,
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color.Black.copy(alpha = 0.7f),
                    )
                }
            }
        }
        OutlinedButton(
            onClick = onClose,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 16.dp),
            contentPadding = PaddingValues(vertical = 14.dp),
        ) {
            Text("Close")
        }
    }
}
