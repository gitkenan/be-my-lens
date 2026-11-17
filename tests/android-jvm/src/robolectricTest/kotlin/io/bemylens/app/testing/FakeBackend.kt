package io.bemylens.app.testing

import io.bemylens.app.BuildConfig
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.assertEquals
import org.junit.rules.ExternalResource
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.ProxySelector
import java.net.SocketAddress
import java.net.URI
import java.util.concurrent.TimeUnit

/**
 * A fake Be My Lens backend for the app's own, unmodified HTTP client.
 *
 * `LensRepository` builds its OkHttp client internally and calls `BuildConfig.API_BASE_URL`
 * (an unresolvable `.test` host in this harness). Installing a [MockWebServer] as the
 * JVM's default HTTP proxy routes those requests here without any production seam, the
 * same way the backend tests fake OpenAI at the transport layer. A request that bypassed
 * the proxy could not resolve its host, so nothing can reach a real server.
 */
class FakeBackend : ExternalResource() {
    private val server = MockWebServer()
    private var previousProxySelector: ProxySelector? = null

    val requestCount: Int get() = server.requestCount

    override fun before() {
        server.start()
        previousProxySelector = ProxySelector.getDefault()
        ProxySelector.setDefault(
            object : ProxySelector() {
                override fun select(uri: URI): List<Proxy> =
                    listOf(Proxy(Proxy.Type.HTTP, InetSocketAddress(server.hostName, server.port)))

                override fun connectFailed(uri: URI, address: SocketAddress, error: IOException) = Unit
            },
        )
    }

    override fun after() {
        ProxySelector.setDefault(previousProxySelector)
        server.shutdown()
    }

    fun respondJson(json: String, status: Int = 200) {
        server.enqueue(
            MockResponse()
                .setResponseCode(status)
                .setHeader("Content-Type", "application/json; charset=utf-8")
                .setBody(json),
        )
    }

    /** The next request the app sent, after checking it went to the configured backend. */
    fun takeRequest(): RecordedRequest {
        val request = server.takeRequest(5, TimeUnit.SECONDS) ?: throw AssertionError("the app sent no request")
        assertEquals(
            "request must go to BuildConfig.API_BASE_URL",
            BuildConfig.API_BASE_URL.toHttpUrl().host,
            request.targetUrl.host,
        )
        return request
    }
}

/**
 * The URL the app asked for. Requests arrive through the proxy in absolute form
 * (`POST http://host/path HTTP/1.1`), which MockWebServer's requestUrl does not reflect.
 */
val RecordedRequest.targetUrl: HttpUrl
    get() = requestLine.split(" ")[1].toHttpUrl()

val RecordedRequest.endpoint: String
    get() = targetUrl.encodedPath
