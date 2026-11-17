package io.bemylens.app.integration

import android.net.Uri

/** An [ExternalImageCommandSource] built from plain values, so parsing can be tested without an Android Intent. */
internal data class FakeCommandSource(
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
