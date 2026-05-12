package android.net

import android.os.Parcel

class FakeUri(
    private val rawValue: String,
) : Uri() {
    private val schemeValue = rawValue.substringBefore("://", missingDelimiterValue = "")

    override fun isHierarchical(): Boolean = true

    override fun isRelative(): Boolean = schemeValue.isBlank()

    override fun getScheme(): String? = schemeValue.takeIf { it.isNotBlank() }

    override fun getSchemeSpecificPart(): String = rawValue.substringAfter(":", missingDelimiterValue = "")

    override fun getEncodedSchemeSpecificPart(): String = schemeSpecificPart

    override fun getAuthority(): String? = null

    override fun getEncodedAuthority(): String? = null

    override fun getUserInfo(): String? = null

    override fun getEncodedUserInfo(): String? = null

    override fun getHost(): String? = null

    override fun getPort(): Int = -1

    override fun getPath(): String? = null

    override fun getEncodedPath(): String? = null

    override fun getQuery(): String? = null

    override fun getEncodedQuery(): String? = null

    override fun getFragment(): String? = null

    override fun getEncodedFragment(): String? = null

    override fun getPathSegments(): List<String> = emptyList()

    override fun getLastPathSegment(): String? = null

    override fun buildUpon(): Builder {
        throw UnsupportedOperationException("FakeUri does not support buildUpon.")
    }

    override fun describeContents(): Int = 0

    override fun writeToParcel(parcel: Parcel, flags: Int) {
        throw UnsupportedOperationException("FakeUri does not support parceling.")
    }

    override fun toString(): String = rawValue
}
