package io.bemylens.app.ui

import android.app.Application
import android.net.Uri
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.bemylens.app.BuildConfig
import io.bemylens.app.ChatMessage
import io.bemylens.app.ChatRole
import io.bemylens.app.data.LensRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LensUiState(
    val selectedImageUri: Uri? = null,
    val isLoading: Boolean = false,
    val latestAnswer: String? = null,
    val sessionId: String? = null,
    val isChatOpen: Boolean = false,
    val followUpQuestion: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val errorMessage: String? = null,
)

class LensViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = LensRepository(application.applicationContext)
    private val _uiState = MutableStateFlow(LensUiState())
    val uiState: StateFlow<LensUiState> = _uiState.asStateFlow()

    fun onImageSelected(uri: Uri) {
        _uiState.update {
            LensUiState(selectedImageUri = uri)
        }
    }

    fun updateFollowUpQuestion(question: String) {
        _uiState.update { it.copy(followUpQuestion = question) }
    }

    fun openChat() {
        _uiState.update { it.copy(isChatOpen = true, errorMessage = null) }
    }

    fun sendShortcut(question: String) {
        _uiState.update { it.copy(followUpQuestion = question) }
        sendFollowUp(question)
    }

    fun describeSelectedImage() {
        val imageUri = _uiState.value.selectedImageUri ?: return

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null) }

            runCatching {
                repository.describeImage(imageUri)
            }.onSuccess { response ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        latestAnswer = response.description,
                        sessionId = response.sessionId,
                        isChatOpen = false,
                        followUpQuestion = "",
                        messages = listOf(
                            ChatMessage(
                                role = ChatRole.ASSISTANT,
                                text = response.description,
                            ),
                        ),
                    )
                }
            }.onFailure { error ->
                Log.e(
                    "BeMyLens",
                    "describeSelectedImage failed in build ${BuildConfig.BUILD_MARKER}",
                    error,
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        errorMessage = errorMessage(
                            error = error,
                            fallback = "Failed to describe image.",
                        ),
                    )
                }
            }
        }
    }

    fun readSelectedImage() {
        val imageUri = _uiState.value.selectedImageUri ?: return

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null) }

            runCatching {
                repository.readContents(imageUri)
            }.onSuccess { response ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        latestAnswer = response.contents,
                        sessionId = response.sessionId,
                        isChatOpen = false,
                        followUpQuestion = "",
                        messages = listOf(
                            ChatMessage(
                                role = ChatRole.ASSISTANT,
                                text = response.contents,
                            ),
                        ),
                    )
                }
            }.onFailure { error ->
                Log.e(
                    "BeMyLens",
                    "readSelectedImage failed in build ${BuildConfig.BUILD_MARKER}",
                    error,
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        errorMessage = errorMessage(
                            error = error,
                            fallback = "Failed to read image contents.",
                        ),
                    )
                }
            }
        }
    }

    fun sendFollowUp(prefilledQuestion: String? = null) {
        val currentState = _uiState.value
        val question = (prefilledQuestion ?: currentState.followUpQuestion).trim()
        val imageUri = currentState.selectedImageUri ?: return
        val sessionId = currentState.sessionId
        if (question.isBlank()) return

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isLoading = true,
                    errorMessage = null,
                    messages = it.messages + ChatMessage(
                        role = ChatRole.USER,
                        text = question,
                    ),
                )
            }

            runCatching {
                if (sessionId == null) {
                    repository.askQuestion(imageUri = imageUri, question = question).let { response ->
                        response.sessionId to response.answer
                    }
                } else {
                    repository.followUp(sessionId = sessionId, question = question).let { response ->
                        sessionId to response.answer
                    }
                }
            }.onSuccess { (newSessionId, answer) ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        followUpQuestion = "",
                        latestAnswer = answer,
                        sessionId = newSessionId,
                        isChatOpen = true,
                        messages = it.messages + ChatMessage(
                            role = ChatRole.ASSISTANT,
                            text = answer,
                        ),
                    )
                }
            }.onFailure { error ->
                Log.e(
                    "BeMyLens",
                    "sendFollowUp failed in build ${BuildConfig.BUILD_MARKER}",
                    error,
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        errorMessage = errorMessage(
                            error = error,
                            fallback = "Failed to send follow-up question.",
                        ),
                        messages = it.messages.dropLast(1),
                    )
                }
            }
        }
    }

    private fun errorMessage(error: Throwable, fallback: String): String {
        if (!BuildConfig.DEBUG) {
            return error.message ?: fallback
        }

        return buildString {
            appendLine("Build: ${BuildConfig.BUILD_MARKER}")
            appendLine("${error::class.java.name}: ${error.message ?: fallback}")
            append(error.stackTraceToString())
        }
    }
}
