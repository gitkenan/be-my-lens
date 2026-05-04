package io.bemylens.app.data

import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.Converter
import retrofit2.Retrofit

class LensJsonTest {
    @Test
    fun convertsDescribeResponseJson() {
        @Suppress("UNCHECKED_CAST")
        val converter = LensJson.converterFactory().responseBodyConverter(
            DescribeResponse::class.java,
            emptyArray(),
            Retrofit.Builder()
                .baseUrl("http://localhost/")
                .build(),
        ) as Converter<ResponseBody, DescribeResponse>

        val response = converter.convert(
            """
            {
              "sessionId": "session-123",
              "description": "A coffee mug on a desk."
            }
            """.trimIndent().toResponseBody("application/json".toMediaType()),
        )

        assertEquals(
            DescribeResponse(
                sessionId = "session-123",
                description = "A coffee mug on a desk.",
            ),
            response,
        )
    }

    @Test
    fun retrofitDescribeMethodConvertsResponse() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "sessionId": "session-456",
                      "description": "A plant beside a window."
                    }
                    """.trimIndent(),
                ),
        )
        server.start()

        try {
            val api = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(LensJson.converterFactory())
                .build()
                .create(LensApi::class.java)

            val response = api.describe(
                MultipartBody.Part.createFormData(
                    name = "image",
                    filename = "image.jpg",
                    body = "image-bytes".toRequestBody("image/jpeg".toMediaType()),
                ),
            )

            assertEquals(
                DescribeResponse(
                    sessionId = "session-456",
                    description = "A plant beside a window.",
                ),
                response,
            )
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun convertsReadContentsResponseJson() {
        @Suppress("UNCHECKED_CAST")
        val converter = LensJson.converterFactory().responseBodyConverter(
            ReadContentsResponse::class.java,
            emptyArray(),
            Retrofit.Builder()
                .baseUrl("http://localhost/")
                .build(),
        ) as Converter<ResponseBody, ReadContentsResponse>

        val response = converter.convert(
            """
            {
              "sessionId": "session-789",
              "contents": "Exit 12A"
            }
            """.trimIndent().toResponseBody("application/json".toMediaType()),
        )

        assertEquals(
            ReadContentsResponse(
                sessionId = "session-789",
                contents = "Exit 12A",
            ),
            response,
        )
    }

    @Test
    fun convertsChatResponseJson() {
        @Suppress("UNCHECKED_CAST")
        val converter = LensJson.converterFactory().responseBodyConverter(
            ChatResponse::class.java,
            emptyArray(),
            Retrofit.Builder()
                .baseUrl("http://localhost/")
                .build(),
        ) as Converter<ResponseBody, ChatResponse>

        val response = converter.convert(
            """
            {
              "sessionId": "session-abc",
              "answer": "The red button is near the top."
            }
            """.trimIndent().toResponseBody("application/json".toMediaType()),
        )

        assertEquals(
            ChatResponse(
                sessionId = "session-abc",
                answer = "The red button is near the top.",
            ),
            response,
        )
    }
}
