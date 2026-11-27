package co.fallsoft.vipi

import android.graphics.BitmapFactory
import android.icu.lang.UCharacter
import android.icu.lang.UProperty
import android.icu.text.BreakIterator
import android.util.Base64
import java.util.UUID
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import org.json.JSONObject

internal data class MessageQuote(
    val message: UUID,
    val sender: UUID,
    val kind: String,
    val excerpt: String,
) {
    fun json() =
        JSONObject()
            .put("message_id", message)
            .put("sender_id", sender)
            .put("kind", kind)
            .put("excerpt", excerpt)
}

internal data class LinkSnapshot(
    val url: String,
    val title: String,
    val thumbnail: String? = null,
) {
    val host
        get() = url.toHttpUrlOrNull()?.host.orEmpty()

    fun json() =
        JSONObject().put("url", url).put("title", title).also {
            if (thumbnail != null) it.put("thumbnail_jpeg", thumbnail)
        }
}

internal data class MessageReaction(
    val message: UUID,
    val sender: UUID,
    val sequence: Int,
    val emoji: String?,
) {
    fun json() =
        JSONObject()
            .put("message_id", message)
            .put("target_sender_id", sender)
            .put("sequence", sequence)
            .put("emoji", emoji ?: JSONObject.NULL)
}

internal data class ChatFeatures(
    val reply: MessageQuote? = null,
    val preview: LinkSnapshot? = null,
    val reaction: MessageReaction? = null,
) {
    fun write(o: JSONObject) {
        if (this == EMPTY) return
        val fields = JSONObject().put("version", 1)
        reply?.let { fields.put("reply", it.json()) }
        preview?.let { fields.put("link_preview", it.json()) }
        reaction?.let { fields.put("reaction", it.json()) }
        o.put("chat_features", fields)
    }

    /**
     * Allow room for Signal framing/padding. Preserve the composed message even when a card will
     * not fit.
     */
    fun writeWire(o: JSONObject) {
        write(o)
        if (preview != null && o.toString().toByteArray().size > 62_000) {
            copy(preview = preview.copy(thumbnail = null)).write(o)
            if (o.toString().toByteArray().size > 62_000) {
                o.remove("chat_features")
                copy(preview = null).write(o)
            }
        }
    }

    companion object {
        val EMPTY = ChatFeatures()
        const val EVENT_BODY = "Reaction"
        private val kinds = setOf("text", "photo", "voice", "video")
        private val urlPattern = Regex("""https://[^\s<>"']+""", RegexOption.IGNORE_CASE)

        fun links(text: String): Sequence<String> =
            urlPattern
                .findAll(text)
                .map { match ->
                    var link = match.value.trimEnd('.', ',', '!', ';')
                    while (
                        link.endsWith(')') && link.count { it == ')' } > link.count { it == '(' }
                    ) link = link.dropLast(1)
                    while (
                        link.endsWith(']') && link.count { it == ']' } > link.count { it == '[' }
                    ) link = link.dropLast(1)
                    link
                }
                .filter { safeLink(it) != null }

        fun safeLink(url: String) =
            url.toHttpUrlOrNull()?.takeIf {
                url.toByteArray().size <= 2048 &&
                    it.isHttps &&
                    it.encodedUsername.isEmpty() &&
                    it.encodedPassword.isEmpty() &&
                    url.substringAfter("://")
                        .substringBefore('/')
                        .substringBefore('?')
                        .substringBefore('#')
                        .contains('@')
                        .not() &&
                    it.port == 443 &&
                    it.host.contains('.') &&
                    listOf(
                            ".local",
                            ".localhost",
                            ".localdomain",
                            ".internal",
                            ".corp",
                            ".lan",
                            ".home.arpa",
                            ".onion",
                        )
                        .none(it.host::endsWith) &&
                    !it.host.all { c -> c.isDigit() || c == '.' } &&
                    !it.host.contains(':') &&
                    url.none(Char::isISOControl)
            }

        fun snippet(text: String): String = buildString {
            var bytes = 0
            val iter = text.codePoints().iterator()
            while (iter.hasNext()) {
                val s = String(Character.toChars(iter.nextInt()))
                bytes += s.toByteArray().size
                if (bytes > 512) break
                append(s)
            }
        }

        fun validEmoji(s: String): Boolean {
            if (s.isBlank() || s.toByteArray().size > 64 || s.any(Char::isISOControl)) return false
            val iter = BreakIterator.getCharacterInstance().apply { setText(s) }
            if (iter.next() != s.length) return false
            return s.codePoints().anyMatch { cp ->
                cp == 0x20e3 || cp > 127 && UCharacter.hasBinaryProperty(cp, UProperty.EMOJI)
            }
        }

        fun thumbnail(value: String?): String? {
            if (value == null || value.length !in 4..10924) return null
            return runCatching {
                val bytes = Base64.decode(value, Base64.NO_WRAP)
                require(bytes.size <= 8192)
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                require(
                    options.outMimeType == "image/jpeg" &&
                        options.outWidth in 1..1024 &&
                        options.outHeight in 1..1024
                )
                value
            }
                .getOrNull()
        }

        fun parse(o: JSONObject, text: String): ChatFeatures {
            val f = o.optJSONObject("chat_features") ?: return EMPTY
            if (f.opt("version") != 1) return EMPTY
            if (f.has("reaction")) {
                val r = f.getJSONObject("reaction")
                require(f.length() == 2 && text == EVENT_BODY && r.has("emoji"))
                val emoji =
                    if (r.isNull("emoji")) null
                    else (r.get("emoji") as String).also { require(validEmoji(it)) }
                val seq =
                    (r.get("sequence") as? Int)?.takeIf { it > 0 }
                        ?: error("Invalid reaction sequence")
                return ChatFeatures(
                    reaction =
                        MessageReaction(
                            r.uuid("message_id"),
                            r.uuid("target_sender_id"),
                            seq,
                            emoji,
                        )
                )
            }
            val quote =
                f.optJSONObject("reply")?.let { q ->
                    runCatching {
                        val excerpt = q.get("excerpt") as String
                        val kind = q.getString("kind")
                        require(kind in kinds && excerpt.toByteArray().size <= 512)
                        MessageQuote(q.uuid("message_id"), q.uuid("sender_id"), kind, excerpt)
                    }
                        .getOrNull()
                }
            val link =
                f.optJSONObject("link_preview")?.let { l ->
                    runCatching {
                        val url = l.getString("url")
                        val title = l.get("title") as String
                        require(
                            title.isNotBlank() &&
                                title.none(Char::isISOControl) &&
                                title.toByteArray().size <= 512 &&
                                url in links(text)
                        )
                        LinkSnapshot(
                            url,
                            title,
                            thumbnail(l.optString("thumbnail_jpeg").takeIf(String::isNotEmpty)),
                        )
                    }
                        .getOrNull()
                }
            return ChatFeatures(quote, link)
        }
    }
}
