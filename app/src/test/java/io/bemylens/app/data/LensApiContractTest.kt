package io.bemylens.app.data

import com.squareup.moshi.JsonDataException
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.MultipartReader
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.http.POST
import java.io.File

/**
 * The app's HTTP client (Retrofit + [LensJson] + [LensApi], as wired in [LensRepository])
 * against a fake backend, checked against `contract/api-contract.json`.
 *
 * The backend suite (`server/tests/test_api_contract.py`) checks the same file from the
 * other side, so a field renamed in either codebase fails a test instead of breaking the
 * app in production.
 */
class LensApiContractTest {
    private val server = MockWebServer()
    private lateinit var api: LensApi

    @Before
    fun setUp() {
        server.start()
        api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .addConverterFactory(LensJson.converterFactory())
            .build()
            .create(LensApi::class.java)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun contractListsExactlyTheEndpointsTheAppCalls() {
        val appPaths = LensApi::class.java.methods
            .mapNotNull { it.getAnnotation(POST::class.java)?.value }
            .map { "/$it" }
            .toSet()

        assertEquals(ApiContract.endpoints.values.map { it.path }.toSet(), appPaths)
    }

    @Test
    fun describeUploadsImageAndReadsDescription() = runBlocking {
        val endpoint = ApiContract.endpoint("describe")
        server.enqueue(endpoint.exampleResponse())

        val response = api.describe(imagePart())

        val request = server.takeRequest()
        assertRoute(endpoint, request)
        assertImageUpload(endpoint, request)
        assertEquals(
            DescribeResponse(
                sessionId = endpoint.response.getValue("sessionId"),
                description = endpoint.response.getValue("description"),
            ),
            response,
        )
    }

    @Test
    fun readContentsUploadsImageAndReadsContents() = runBlocking {
        val endpoint = ApiContract.endpoint("read")
        server.enqueue(endpoint.exampleResponse())

        val response = api.readContents(imagePart())

        val request = server.takeRequest()
        assertRoute(endpoint, request)
        assertImageUpload(endpoint, request)
        assertEquals(
            ReadContentsResponse(
                sessionId = endpoint.response.getValue("sessionId"),
                contents = endpoint.response.getValue("contents"),
            ),
            response,
        )
    }

    @Test
    fun askQuestionUploadsImageWithUtf8QuestionAndReadsAnswer() = runBlocking {
        val endpoint = ApiContract.endpoint("chat")
        server.enqueue(endpoint.exampleResponse())
        val question = "ما المكتوب على اللافتة؟"

        val response = api.askQuestion(imagePart(), question.toRequestBody("text/plain".toMediaType()))

        val request = server.takeRequest()
        assertRoute(endpoint, request)
        val parts = assertImageUpload(endpoint, request)
        assertEquals(question, parts.getValue("question").body.toString(Charsets.UTF_8))
        assertEquals(
            ChatResponse(
                sessionId = endpoint.response.getValue("sessionId"),
                answer = endpoint.response.getValue("answer"),
            ),
            response,
        )
    }

    @Test
    fun followUpSendsSessionAndQuestionAsJsonAndReadsAnswer() = runBlocking {
        val endpoint = ApiContract.endpoint("followup")
        server.enqueue(endpoint.exampleResponse())
        val body = endpoint.jsonBody

        val response = api.followUp(
            FollowUpRequest(sessionId = body.getValue("sessionId"), question = body.getValue("question")),
        )

        val request = server.takeRequest()
        assertRoute(endpoint, request)
        assertEquals(body, ApiContract.parseObject(request.body.readUtf8()))
        assertEquals(FollowUpResponse(answer = endpoint.response.getValue("answer")), response)
    }

    @Test
    fun translateTextSendsTextAsJsonAndReadsAnswer() = runBlocking {
        val endpoint = ApiContract.endpoint("translate_text")
        server.enqueue(endpoint.exampleResponse())

        val response = api.translateText(TranslateTextRequest(text = endpoint.jsonBody.getValue("text")))

        val request = server.takeRequest()
        assertRoute(endpoint, request)
        assertEquals(endpoint.jsonBody, ApiContract.parseObject(request.body.readUtf8()))
        assertEquals(TranslateTextResponse(answer = endpoint.response.getValue("answer")), response)
    }

    @Test
    fun backendFailureSurfacesAsHttpErrorWithStatus() {
        server.enqueue(
            MockResponse()
                .setResponseCode(502)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail": "upstream said no"}"""),
        )

        val error = assertThrows(HttpException::class.java) {
            runBlocking { api.describe(imagePart()) }
        }

        assertEquals(502, error.code())
    }

    @Test
    fun expiredSessionSurfacesAsNotFound() {
        // Sessions live in backend memory, so every restart or deploy expires them.
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail": "session not found"}"""))

        val error = assertThrows(HttpException::class.java) {
            runBlocking { api.followUp(FollowUpRequest(sessionId = "gone", question = "Hello?")) }
        }

        assertEquals(404, error.code())
    }

    @Test
    fun responseMissingARequiredFieldFailsInsteadOfYieldingNull() {
        server.enqueue(jsonResponse("""{"sessionId": "abc"}"""))

        assertThrows(JsonDataException::class.java) {
            runBlocking { api.describe(imagePart()) }
        }
    }

    @Test
    fun unknownResponseFieldsAreIgnoredSoTheBackendCanGrow() = runBlocking {
        server.enqueue(jsonResponse("""{"answer": "مرحبا", "model": "gpt-4.1-mini", "usage": {"tokens": 12}}"""))

        val response = api.translateText(TranslateTextRequest(text = "hello"))

        assertEquals(TranslateTextResponse(answer = "مرحبا"), response)
    }

    private fun assertRoute(endpoint: ContractEndpoint, request: RecordedRequest) {
        assertEquals(endpoint.method, request.method)
        assertEquals(endpoint.path, request.path)
    }

    /** Checks the multipart fields match the contract and the image arrives intact as a JPEG. */
    private fun assertImageUpload(endpoint: ContractEndpoint, request: RecordedRequest): Map<String, FormPart> {
        val parts = readMultipart(request)
        assertEquals(endpoint.multipartFields, parts.keys.toList())
        val image = parts.getValue("image")
        assertEquals("image.jpg", image.filename)
        assertEquals("image/jpeg", image.contentType)
        assertArrayEquals(IMAGE_BYTES, image.body)
        return parts
    }

    private class FormPart(val filename: String?, val contentType: String?, val body: ByteArray)

    private fun readMultipart(request: RecordedRequest): Map<String, FormPart> {
        val contentType = request.getHeader("Content-Type")!!.toMediaType()
        assertEquals("multipart/form-data", "${contentType.type}/${contentType.subtype}")
        val parts = linkedMapOf<String, FormPart>()
        MultipartReader(request.body, contentType.parameter("boundary")!!).use { reader ->
            while (true) {
                val part = reader.nextPart() ?: break
                val disposition = part.headers["Content-Disposition"].orEmpty()
                val name = Regex("""\bname="([^"]*)"""").find(disposition)!!.groupValues[1]
                parts[name] = FormPart(
                    filename = Regex("""filename="([^"]*)"""").find(disposition)?.groupValues?.get(1),
                    contentType = part.headers["Content-Type"],
                    body = part.body.readByteArray(),
                )
            }
        }
        assertTrue("no multipart fields were sent", parts.isNotEmpty())
        return parts
    }

    private companion object {
        val IMAGE_BYTES = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte(), 0xE0.toByte(), 1, 2, 3, 4)

        /** Built the same way as LensRepository.imagePartFor. */
        fun imagePart(): MultipartBody.Part = MultipartBody.Part.createFormData(
            name = "image",
            filename = "image.jpg",
            body = IMAGE_BYTES.toRequestBody("image/jpeg".toMediaType()),
        )

        fun jsonResponse(json: String): MockResponse = MockResponse()
            .setHeader("Content-Type", "application/json; charset=utf-8")
            .setBody(json)

        fun ContractEndpoint.exampleResponse(): MockResponse = jsonResponse(ApiContract.toJson(response))
    }
}

private class ContractEndpoint(
    val method: String,
    val path: String,
    val multipartFields: List<String>,
    val jsonBody: Map<String, String>,
    val response: Map<String, String>,
)

/** Reads `contract/api-contract.json` from the repository root. */
private object ApiContract {
    private val moshi = Moshi.Builder().build()
    private val objectAdapter = moshi.adapter<Map<String, Any?>>(
        Types.newParameterizedType(Map::class.java, String::class.java, Any::class.java),
    )

    val endpoints: Map<String, ContractEndpoint> by lazy {
        @Suppress("UNCHECKED_CAST")
        val raw = parseObject(findContractFile().readText())["endpoints"] as Map<String, Map<String, Any?>>
        raw.mapValues { (_, endpoint) ->
            ContractEndpoint(
                method = endpoint["method"] as String,
                path = endpoint["path"] as String,
                multipartFields = endpoint.strings("multipartFields"),
                jsonBody = endpoint.stringMap("jsonBody"),
                response = endpoint.stringMap("response"),
            )
        }
    }

    fun endpoint(name: String): ContractEndpoint = endpoints.getValue(name)

    fun parseObject(json: String): Map<String, Any?> = objectAdapter.fromJson(json)!!

    fun toJson(value: Map<String, String>): String = objectAdapter.toJson(value)

    @Suppress("UNCHECKED_CAST")
    private fun Map<String, Any?>.strings(key: String): List<String> = (this[key] as List<String>?).orEmpty()

    @Suppress("UNCHECKED_CAST")
    private fun Map<String, Any?>.stringMap(key: String): Map<String, String> =
        (this[key] as Map<String, String>?).orEmpty()

    /** Works whether tests run from the app module (Gradle, Android Studio) or the repo root. */
    private fun findContractFile(): File {
        val start = File("").absoluteFile
        return generateSequence(start) { it.parentFile }
            .map { File(it, "contract/api-contract.json") }
            .firstOrNull { it.isFile }
            ?: error("contract/api-contract.json not found in ${start.path} or any parent directory")
    }
}
