package io.bemylens.app

enum class ChatRole {
    USER,
    ASSISTANT,
}

data class ChatMessage(
    val role: ChatRole,
    val text: String,
)
