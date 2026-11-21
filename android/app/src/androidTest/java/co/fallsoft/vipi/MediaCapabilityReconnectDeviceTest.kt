package co.fallsoft.vipi

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.util.UUID

class MediaCapabilityReconnectDeviceTest {
    @Test fun onlyTheAuthenticatedPeerLookupReconnectsOnce() = runBlocking {
        JourneyServices(false).use { service ->
            MainActivityJourneyFixture("media-capability-reconnect", service::model).use { fixture ->
                ServerSocket(0, 8, InetAddress.getByName("127.0.0.1")).use { listener ->
                    listener.soTimeout = 8000
                    val device = DeviceCredential(UUID.randomUUID(), "synthetic-test-only")
                    val path = "/v1/media/capability/${UUID.randomUUID()}"
                    val lookup = "GET $path HTTP/1.1"
                    val paths = listOf(lookup, lookup, lookup, lookup, "PUT /v1/media/capability HTTP/1.1", "GET /v1/me HTTP/1.1", lookup)
                    val observed = async(Dispatchers.IO) {
                        paths.forEachIndexed { i, expected ->
                            listener.accept().use { socket ->
                                socket.soTimeout = 5000
                                val input = socket.getInputStream().bufferedReader(Charsets.US_ASCII)
                                assertEquals(expected, input.readLine())
                                val headers = generateSequence { input.readLine().takeUnless { it.isNullOrEmpty() } }.toList()
                                assertTrue(headers.any { it == "Authorization: Bearer synthetic-inert-access" })
                                assertTrue(headers.any { it == "X-Vipi-Device-ID: ${device.id}" })
                                if (i == 1 || i == paths.lastIndex) {
                                    val body = if (i == 1) """{"version":1}""" else """{"error":"unavailable"}"""
                                    val status = if (i == 1) "200 OK" else "404 Not Found"
                                    socket.getOutputStream().write(("HTTP/1.1 $status\r\nConnection: close\r\n" +
                                        "Content-Length: ${body.length}\r\n\r\n$body").toByteArray(Charsets.US_ASCII))
                                }
                            }
                        }
                    }
                    val api = ServiceClient(fixture.model.authentication, service.subject, "http://127.0.0.1:${listener.localPort}")
                    assertEquals(1, api.request("GET", path, device = device).getInt("version"))
                    assertTrue(runCatching { api.request("GET", path, device = device) }.exceptionOrNull() is IOException)
                    assertTrue(runCatching { api.request("PUT", "/v1/media/capability", JSONObject().put("version", 1), device) }.exceptionOrNull() is IOException)
                    assertTrue(runCatching { api.request("GET", "/v1/me", device = device) }.exceptionOrNull() is IOException)
                    val unsupported = runCatching { api.request("GET", path, device = device) }.exceptionOrNull()
                    assertEquals(404, (unsupported as ServiceFailure).status)
                    observed.await()
                }
            }
        }
    }
}
