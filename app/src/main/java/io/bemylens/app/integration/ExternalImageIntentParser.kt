package io.bemylens.app.integration

import android.content.Intent
import android.net.Uri
import android.os.Build
import io.bemylens.app.integration.ExternalIntegrationContract.Extras
import io.bemylens.app.integration.ExternalIntegrationContract.Modes

data class ExternalImageCommand(
    val mode: String,
    val imageUri: Uri?,
    val prompt: String?,
    val autoSpeak: Boolean,
)

enum class ExternalImageCommandError {
    UNSUPPORTED_MODE,
    CUSTOM_PROMPT_REQUIRED,
    NO_IMAGE_RECEIVED,
}

class ExternalImageCommandException(
    val error: ExternalImageCommandError,
    val value: String? = null,
) : IllegalArgumentException(error.name)

object ExternalImageIntentParser {
    fun parse(intent: Intent): ExternalImageCommand {
        return parse(AndroidIntentCommandSource(intent))
    }

    fun parse(source: ExternalImageCommandSource): ExternalImageCommand {
        val mode = source.getStringExtra(Extras.MODE)
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?: Modes.DESCRIBE_SCREEN

        if (mode !in Modes.SUPPORTED) {
            throw ExternalImageCommandException(
                error = ExternalImageCommandError.UNSUPPORTED_MODE,
                value = mode,
            )
        }

        val prompt = source.getStringExtra(Extras.PROMPT)
            ?.trim()
            ?.takeIf { it.isNotBlank() }

        if (mode == Modes.CUSTOM_PROMPT && prompt == null) {
            throw ExternalImageCommandException(
                error = ExternalImageCommandError.CUSTOM_PROMPT_REQUIRED,
            )
        }

        val imageUri = source.receivedImageUri()
            ?: throw ExternalImageCommandException(
                error = ExternalImageCommandError.NO_IMAGE_RECEIVED,
            )

        return ExternalImageCommand(
            mode = mode,
            imageUri = imageUri,
            prompt = prompt,
            autoSpeak = source.getBooleanExtra(Extras.AUTO_SPEAK, true),
        )
    }
}

interface ExternalImageCommandSource {
    val streamUri: Uri?
    val customImageUri: Uri?
    val customImageUriString: String?
    val dataUri: Uri?

    fun getStringExtra(key: String): String?
    fun getBooleanExtra(key: String, defaultValue: Boolean): Boolean

    fun receivedImageUri(): Uri? {
        return streamUri
            ?: customImageUri
            ?: customImageUriString?.let(Uri::parse)
            ?: dataUri
    }
}

private class AndroidIntentCommandSource(
    private val intent: Intent,
) : ExternalImageCommandSource {
    override val streamUri: Uri?
        get() = intent.streamExtraUri()

    override val customImageUri: Uri?
        get() = intent.customImageUriExtra()

    override val customImageUriString: String?
        get() = intent.getStringExtra(Extras.IMAGE_URI)

    override val dataUri: Uri?
        get() = intent.data

    override fun getStringExtra(key: String): String? {
        return intent.getStringExtra(key)
    }

    override fun getBooleanExtra(key: String, defaultValue: Boolean): Boolean {
        return intent.getBooleanExtra(key, defaultValue)
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
            getParcelableExtra(Extras.IMAGE_URI, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            getParcelableExtra(Extras.IMAGE_URI)
        }
        return parcelableUri
    }
}
