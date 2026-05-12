package io.bemylens.app.integration

object ExternalIntegrationContract {
    const val ACTION_DESCRIBE_IMAGE = "io.bemylens.app.action.DESCRIBE_IMAGE"

    object Extras {
        const val IMAGE_URI = "io.bemylens.app.extra.IMAGE_URI"
        const val MODE = "mode"
        const val PROMPT = "prompt"
        const val AUTO_SPEAK = "autoSpeak"
    }

    object Modes {
        const val DESCRIBE_SCREEN = "describe_screen"
        const val FOCUSED_ITEM = "focused_item"
        const val READ_TEXT = "read_text"
        const val CUSTOM_PROMPT = "custom_prompt"

        val SUPPORTED = setOf(
            DESCRIBE_SCREEN,
            FOCUSED_ITEM,
            READ_TEXT,
            CUSTOM_PROMPT,
        )
    }

    const val FOCUSED_ITEM_DEFAULT_PROMPT =
        "Describe only the focused item or control. Ignore unrelated background content unless necessary."
}
