package co.fallsoft.vipi

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.text.Html
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Dns
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.Proxy
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

/** This client is invoked exclusively by the composer. It has no auth headers, cookies, disk cache,
 * proxy, scripts or subresource loader. Validate the addresses on the lookup used by the socket. */
internal object SenderLinkPreview {
    internal fun publicAddress(address: InetAddress): Boolean {
        if (address.isAnyLocalAddress || address.isLoopbackAddress || address.isLinkLocalAddress ||
            address.isSiteLocalAddress || address.isMulticastAddress) return false
        val a = address.address.map { it.toInt() and 255 }
        if (a.size == 16) return (a[0] in 0x20..0x3f) && !(a[0] == 0x20 && a[1] in 1..2)
        return a[0] !in setOf(0, 10, 127) && a[0] < 224 &&
            !(a[0] == 100 && a[1] in 64..127) && !(a[0] == 169 && a[1] == 254) &&
            !(a[0] == 172 && a[1] in 16..31) && !(a[0] == 192 && (a[1] in setOf(0, 168) || a[1] == 88 && a[2] == 99)) &&
            !(a[0] == 198 && (a[1] in 18..19 || a[1] == 51 && a[2] == 100)) && !(a[0] == 203 && a[1] == 0 && a[2] == 113)
    }

    private val client = OkHttpClient.Builder().proxy(Proxy.NO_PROXY).dns(object : Dns {
        override fun lookup(hostname: String): List<InetAddress> = Dns.SYSTEM.lookup(hostname).also { addresses ->
            if (addresses.isEmpty() || addresses.any { !publicAddress(it) }) throw UnknownHostException()
        }
    }).followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
        .callTimeout(4, TimeUnit.SECONDS).build()

    private data class Resource(val url: HttpUrl, val bytes: ByteArray)
    private fun read(url: HttpUrl, image: Boolean, origin: HttpUrl = url): Resource? {
        var current = url
        val limit = if (image) 256 * 1024 else 96 * 1024
        repeat(3) {
            if (ChatFeatures.safeLink(current.toString()) == null || image && current.host != origin.host) return null
            val request = Request.Builder().url(current).header("Accept", if (image) "image/jpeg,image/png,image/webp" else "text/html").build()
            client.newCall(request).execute().use { response ->
                if (response.code in setOf(301, 302, 303, 307, 308)) {
                    current = current.resolve(response.header("Location") ?: return null) ?: return null
                } else {
                    val body = response.body ?: return null
                    val mime = body.contentType()
                    if (!response.isSuccessful || if (image) mime?.type != "image" else mime?.subtype != "html") return null
                    if (image && body.contentLength() > limit) return null
                    val source = body.source()
                    val over = source.request(limit + 1L)
                    if (image && over) return null
                    return Resource(current, source.readByteArray(minOf(source.buffer.size, limit.toLong())))
                }
            }
        }
        return null
    }

    private val meta = Regex("""<meta\b[^>]{0,4096}>""", RegexOption.IGNORE_CASE)
    private val attribute = Regex("""([A-Za-z:-]+)\s*=\s*["']([^"']{0,2048})["']""")
    private val htmlTitle = Regex("""(?is)<title\b[^>]*>(.{1,2048}?)</title\s*>""")
    private fun decoded(value: String) = Html.fromHtml(value, Html.FROM_HTML_MODE_LEGACY).toString().replace(Regex("""\s+"""), " ").trim()

    internal fun metadata(html: String): Pair<String?, String?> {
        val properties = meta.findAll(html).take(128).mapNotNull { tag ->
            val attrs = attribute.findAll(tag.value).associate { it.groupValues[1].lowercase() to it.groupValues[2] }
            val key = attrs["property"] ?: attrs["name"] ?: return@mapNotNull null
            key.lowercase() to attrs["content"].orEmpty()
        }.toMap()
        val title = properties["og:title"]?.takeIf(String::isNotBlank) ?: htmlTitle.find(html)?.groupValues?.get(1)
        return title?.let(::decoded)?.let(ChatFeatures::snippet)?.takeIf(String::isNotBlank) to properties["og:image"]?.let(::decoded)
    }

    suspend fun load(url: String): LinkSnapshot? = withContext(Dispatchers.IO) {
        val initial = ChatFeatures.safeLink(url) ?: return@withContext null
        val page = read(initial, false) ?: return@withContext null
        val (title, imageURL) = metadata(page.bytes.toString(Charsets.UTF_8))
        if (title == null) return@withContext null
        val thumbnail = imageURL?.let(page.url::resolve)?.takeIf { it.host == initial.host }?.let { image ->
            runCatching { read(image, true, initial)?.let { thumbnail(it.bytes) } }.getOrNull()
        }
        LinkSnapshot(url, title, thumbnail)
    }

    private fun thumbnail(bytes: ByteArray): String? {
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
        if (opts.outWidth !in 1..8192 || opts.outHeight !in 1..8192) return null
        opts.inJustDecodeBounds = false
        while (maxOf(opts.outWidth, opts.outHeight) / opts.inSampleSize.coerceAtLeast(1) > 144)
            opts.inSampleSize = opts.inSampleSize.coerceAtLeast(1) * 2
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return null
        return try {
            for (quality in listOf(75, 50, 30)) {
                val out = ByteArrayOutputStream()
                if (bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out) && out.size() <= 8192)
                    return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            }
            null
        } finally { bitmap.recycle() }
    }
}
