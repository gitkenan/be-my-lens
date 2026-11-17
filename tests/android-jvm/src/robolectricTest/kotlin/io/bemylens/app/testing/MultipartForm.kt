package io.bemylens.app.testing

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartReader
import okhttp3.mockwebserver.RecordedRequest

/** One field of a multipart/form-data request the app sent. */
class FormField(val filename: String?, val contentType: String?, val body: ByteArray) {
    val text: String get() = body.toString(Charsets.UTF_8)
}

fun RecordedRequest.multipartFields(): Map<String, FormField> {
    val contentType = getHeader("Content-Type")!!.toMediaType()
    check("${contentType.type}/${contentType.subtype}" == "multipart/form-data") { "not multipart: $contentType" }
    val fields = linkedMapOf<String, FormField>()
    MultipartReader(body, contentType.parameter("boundary")!!).use { reader ->
        while (true) {
            val part = reader.nextPart() ?: break
            val disposition = part.headers["Content-Disposition"].orEmpty()
            val name = Regex("""\bname="([^"]*)"""").find(disposition)!!.groupValues[1]
            fields[name] = FormField(
                filename = Regex("""filename="([^"]*)"""").find(disposition)?.groupValues?.get(1),
                contentType = part.headers["Content-Type"],
                body = part.body.readByteArray(),
            )
        }
    }
    return fields
}
