package io.bemylens.app

import android.content.Intent
import android.net.Uri
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import io.bemylens.app.data.LensRepository
import io.bemylens.app.integration.ExternalImageCommand
import io.bemylens.app.integration.ExternalImageCommandError
import io.bemylens.app.integration.ExternalImageCommandException
import io.bemylens.app.integration.ExternalImageIntentParser
import io.bemylens.app.integration.ExternalIntegrationContract.Modes
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
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
                val command = ExternalImageIntentParser.parse(intent)
                val imageUri = command.imageUri
                    ?: throw ExternalImageCommandException(
                        error = ExternalImageCommandError.NO_IMAGE_RECEIVED,
                    )
                validateImageType(intent, imageUri)

                val cachedImageUri = withContext(Dispatchers.IO) {
                    copyImageToCache(imageUri)
                }

                val answer = processCommand(command, cachedImageUri)

                JieshuoScreenState.Result(
                    answer = answer,
                    mode = command.mode,
                    prompt = command.prompt,
                    autoSpeak = command.autoSpeak,
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

    private fun validateImageType(intent: Intent, imageUri: Uri) {
        val type = intent.type ?: contentResolver.getType(imageUri)
        if (type != null && !type.startsWith("image/")) {
            throw JieshuoInputException(getString(R.string.error_unsupported_content_type, type))
        }
    }

    private suspend fun processCommand(command: ExternalImageCommand, cachedImageUri: Uri): String {
        return when (command.mode) {
            Modes.DESCRIBE_SCREEN -> {
                command.prompt?.let { prompt ->
                    repository.askQuestion(cachedImageUri, prompt).answer
                } ?: repository.describeImage(cachedImageUri).description
            }
            Modes.FOCUSED_ITEM -> {
                repository.askQuestion(
                    imageUri = cachedImageUri,
                    question = command.prompt ?: getString(R.string.prompt_focused_item_default),
                ).answer
            }
            Modes.READ_TEXT -> {
                command.prompt?.let { prompt ->
                    repository.askQuestion(cachedImageUri, prompt).answer
                } ?: repository.readContents(cachedImageUri).contents
            }
            Modes.CUSTOM_PROMPT -> {
                repository.askQuestion(
                    imageUri = cachedImageUri,
                    question = command.prompt
                        ?: throw ExternalImageCommandException(
                            error = ExternalImageCommandError.CUSTOM_PROMPT_REQUIRED,
                        ),
                ).answer
            }
            else -> throw ExternalImageCommandException(
                error = ExternalImageCommandError.UNSUPPORTED_MODE,
                value = command.mode,
            )
        }
    }

    private fun copyImageToCache(sourceUri: Uri): Uri {
        val scheme = sourceUri.scheme
        if (scheme != "content" && scheme != "file") {
            throw JieshuoInputException(
                getString(
                    R.string.error_unsupported_image_uri,
                    sourceUri.scheme ?: getString(R.string.error_unknown_image_uri_scheme),
                ),
            )
        }

        val incomingDir = File(cacheDir, "jieshuo").apply { mkdirs() }
        val imageFile = File.createTempFile("incoming_", ".jpg", incomingDir)

        try {
            contentResolver.openInputStream(sourceUri)?.use { input ->
                imageFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            } ?: throw JieshuoInputException(getString(R.string.error_unable_open_received_image))
        } catch (error: SecurityException) {
            throw JieshuoInputException(getString(R.string.error_no_received_image_permission), error)
        } catch (error: IOException) {
            throw JieshuoInputException(getString(R.string.error_unable_copy_received_image), error)
        }

        return Uri.fromFile(imageFile)
    }

    private fun Throwable.toJieshuoErrorState(): JieshuoScreenState.Error {
        val message = when (this) {
            is JieshuoInputException -> message ?: getString(R.string.error_unable_use_received_image)
            is ExternalImageCommandException -> localizedExternalCommandMessage()
            else -> getString(R.string.error_processing_failed)
        }

        return JieshuoScreenState.Error(
            message = message,
            detail = this.cause?.message
                ?: takeUnless {
                    it is JieshuoInputException || it is ExternalImageCommandException
                }?.message,
        )
    }

    private fun ExternalImageCommandException.localizedExternalCommandMessage(): String {
        return when (error) {
            ExternalImageCommandError.UNSUPPORTED_MODE -> getString(
                R.string.error_unsupported_mode_with_supported,
                value ?: "",
                Modes.SUPPORTED.joinToString(),
            )
            ExternalImageCommandError.CUSTOM_PROMPT_REQUIRED -> {
                getString(R.string.error_custom_prompt_required)
            }
            ExternalImageCommandError.NO_IMAGE_RECEIVED -> getString(R.string.error_no_image_received)
        }
    }

    private fun speak(text: String) {
        if (!ttsReady) {
            pendingSpeech = text
            return
        }

        speaker?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "be-my-lens-jieshuo")
    }
}

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
            text = stringResource(R.string.jieshuo_processing),
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
            text = stringResource(R.string.app_name),
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
                    text = if (state.prompt == null) {
                        stringResource(R.string.result_description)
                    } else {
                        stringResource(R.string.result_answer)
                    },
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
            Text(stringResource(R.string.action_read_aloud))
        }
        OutlinedButton(
            onClick = onClose,
            modifier = Modifier.fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 14.dp),
        ) {
            Text(stringResource(R.string.action_close))
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
                    text = stringResource(R.string.error_unable_describe_image),
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
            Text(stringResource(R.string.action_close))
        }
    }
}
