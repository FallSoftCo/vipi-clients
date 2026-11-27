package co.fallsoft.vipi

import android.util.JsonReader
import android.util.JsonToken
import java.io.*
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.security.SecureRandom
import java.text.Normalizer
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject

/** Portable history only. No authentication, device identity, Signal state or pending sends. */
internal object HistoryBackupCodec {
    const val MAX_FILE_BYTES = 1_073_741_824L
    private const val MAX_CLEAR = 262_144
    private const val MAX_RECORDS = 200_000
    private const val ITERATIONS = 600_000
    private val magic = "VIPIHST1".toByteArray(Charsets.US_ASCII)

    data class Summary(val peers: Int, val messages: Int)

    data class Inspection(val summary: Summary, val sha256: String)

    class DifferentAccount : IOException("This backup belongs to another Vipi account")

    private fun strictUTF8(value: String): ByteArray {
        val encoded =
            Charsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(java.nio.CharBuffer.wrap(value))
        return ByteArray(encoded.remaining()).also(encoded::get)
    }

    fun validPassword(password: String): Boolean = runCatching {
        val value = Normalizer.normalize(password, Normalizer.Form.NFC)
        require(value.codePointCount(0, value.length) >= 12 && strictUTF8(value).size in 12..1024)
    }
        .isSuccess

    private fun derive(password: String, salt: ByteArray): ByteArray {
        require(validPassword(password))
        val chars = Normalizer.normalize(password, Normalizer.Form.NFC).toCharArray()
        val spec = PBEKeySpec(chars, salt, ITERATIONS, 256)
        return try {
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
            chars.fill('\u0000')
        }
    }

    private fun intBytes(value: Int) = ByteBuffer.allocate(4).putInt(value).array()

    private fun crypt(
        mode: Int,
        key: ByteArray,
        header: ByteArray,
        index: Int,
        length: ByteArray,
        value: ByteArray,
    ): ByteArray =
        Cipher.getInstance("AES/GCM/NoPadding").run {
            init(
                mode,
                SecretKeySpec(key, "AES"),
                GCMParameterSpec(128, header.copyOfRange(28, 36) + intBytes(index)),
            )
            updateAAD(header + intBytes(index) + length)
            doFinal(value)
        }

    private fun parse(bytes: ByteArray): JSONObject {
        val text =
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString()
        return JsonReader(StringReader(text)).use { reader ->
            reader.isLenient = false
            reader.beginObject()
            val value = JSONObject()
            val seen = mutableSetOf<String>()
            while (reader.hasNext()) {
                val name = reader.nextName()
                require(seen.add(name))
                val next: Any =
                    when (reader.peek()) {
                        JsonToken.STRING -> reader.nextString().also { strictUTF8(it) }
                        JsonToken.NUMBER ->
                            reader
                                .nextString()
                                .also { require(it.matches(Regex("0|[1-9][0-9]*"))) }
                                .toLong()
                        JsonToken.NULL -> {
                            reader.nextNull()
                            JSONObject.NULL
                        }
                        else -> throw IOException("Invalid backup record")
                    }
                value.put(name, next)
            }
            reader.endObject()
            require(reader.peek() == JsonToken.END_DOCUMENT)
            value
        }
    }

    private class Validation(private val account: UUID) {
        var count = 0
            private set

        var ended = false
            private set

        private val peers = mutableSetOf<UUID>()
        private val messages = mutableSetOf<UUID>()
        val summary
            get() = Summary(peers.size, messages.size)

        private fun schema(row: JSONObject, vararg fields: String) {
            require(row.keys().asSequence().toSet() == fields.toSet())
        }

        private fun uuid(row: JSONObject, field: String): UUID {
            val raw = row.get(field)
            require(raw is String)
            return UUID.fromString(raw).also { require(it.toString() == raw) }
        }

        private fun number(row: JSONObject, field: String, max: Long = 253_402_300_799_999): Long {
            val value = row.get(field)
            require(value is Int || value is Long)
            return (value as Number).toLong().also { require(it in 0..max) }
        }

        fun accept(row: JSONObject) {
            require(!ended && count < MAX_RECORDS)
            when (row.getString("type")) {
                "metadata" -> {
                    require(count == 0)
                    schema(row, "type", "version", "account_id", "created_at_ms")
                    require(number(row, "version") == 1L)
                    if (uuid(row, "account_id") != account) throw DifferentAccount()
                    number(row, "created_at_ms")
                }
                "peer" -> {
                    require(count > 0 && messages.isEmpty())
                    schema(row, "type", "id", "username", "display_name")
                    val peer = uuid(row, "id")
                    require(peer != account && peers.add(peer))
                    val username = row.get("username")
                    val name = row.get("display_name")
                    if (username != JSONObject.NULL) {
                        require(
                            username is String && username.matches(Regex("[a-z][a-z0-9_]{2,23}"))
                        )
                    }
                    if (name != JSONObject.NULL) {
                        require(name is String && name.codePointCount(0, name.length) in 1..80)
                        strictUTF8(name)
                        name.codePoints().forEach { cp ->
                            require(
                                Character.getType(cp) !in
                                    setOf(
                                        Character.CONTROL.toInt(),
                                        Character.FORMAT.toInt(),
                                        Character.SURROGATE.toInt(),
                                        Character.PRIVATE_USE.toInt(),
                                        Character.UNASSIGNED.toInt(),
                                    )
                            )
                        }
                    }
                }
                "message" -> {
                    require(count > 0)
                    schema(row, "type", "id", "peer_id", "direction", "sent_at_ms", "text")
                    require(messages.add(uuid(row, "id")) && uuid(row, "peer_id") in peers)
                    require(row.get("direction") in setOf("incoming", "outgoing"))
                    number(row, "sent_at_ms")
                    val text = row.get("text")
                    require(text is String && text.isNotBlank() && strictUTF8(text).size <= 32768)
                }
                "end" -> {
                    require(count > 0)
                    schema(row, "type", "record_count", "peer_count", "message_count")
                    require(
                        number(row, "record_count", MAX_RECORDS.toLong()) == count.toLong() &&
                            number(row, "peer_count", MAX_RECORDS.toLong()) ==
                                peers.size.toLong() &&
                            number(row, "message_count", MAX_RECORDS.toLong()) ==
                                messages.size.toLong()
                    )
                    ended = true
                }
                else -> throw IOException("Unsupported backup record")
            }
            count++
        }
    }

    /** Callback may stage writes only inside a rollback-capable transaction. */
    fun inspect(
        file: File,
        password: String,
        account: UUID,
        check: () -> Unit = {},
        record: (JSONObject) -> Unit = {},
    ): Inspection {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        val summary = read(file, password, account, check, record, digest)
        return Inspection(summary, digest.digest().joinToString("") { "%02x".format(it) })
    }

    fun read(
        file: File,
        password: String,
        account: UUID,
        check: () -> Unit = {},
        record: (JSONObject) -> Unit = {},
        digest: java.security.MessageDigest? = null,
    ): Summary {
        require(file.length() in 56..MAX_FILE_BYTES)
        val validation = Validation(account)
        val raw = FileInputStream(file)
        DataInputStream(
                BufferedInputStream(
                    if (digest == null) raw else java.security.DigestInputStream(raw, digest)
                )
            )
            .use { input ->
                val header = ByteArray(36).also(input::readFully)
                require(
                    header.copyOfRange(0, 8).contentEquals(magic) &&
                        ByteBuffer.wrap(header, 8, 4).int == ITERATIONS
                )
                val key = derive(password, header.copyOfRange(12, 28))
                try {
                    while (!validation.ended) {
                        check()
                        val length = input.readInt()
                        require(length in 17..(MAX_CLEAR + 16))
                        val encrypted = ByteArray(length).also(input::readFully)
                        val clear =
                            crypt(
                                Cipher.DECRYPT_MODE,
                                key,
                                header,
                                validation.count,
                                intBytes(length),
                                encrypted,
                            )
                        val row =
                            try {
                                parse(clear)
                            } finally {
                                clear.fill(0)
                            }
                        validation.accept(row)
                        record(row)
                    }
                    require(input.read() == -1)
                    check()
                } finally {
                    key.fill(0)
                }
            }
        return validation.summary
    }

    fun write(
        file: File,
        password: String,
        account: UUID,
        check: () -> Unit = {},
        records: ((JSONObject) -> Unit) -> Unit,
    ): Summary {
        val random = SecureRandom()
        val salt = ByteArray(16).also(random::nextBytes)
        val prefix = ByteArray(8).also(random::nextBytes)
        val header = magic + intBytes(ITERATIONS) + salt + prefix
        val key = derive(password, salt)
        val validation = Validation(account)
        var bytes = 36L
        try {
            FileOutputStream(file).use { raw ->
                val output = DataOutputStream(BufferedOutputStream(raw))
                output.write(header)
                fun emit(row: JSONObject) {
                    check()
                    val index = validation.count
                    validation.accept(row)
                    val clear = strictUTF8(row.toString())
                    require(clear.size <= MAX_CLEAR)
                    val length = intBytes(clear.size + 16)
                    val encrypted =
                        try {
                            crypt(Cipher.ENCRYPT_MODE, key, header, index, length, clear)
                        } finally {
                            clear.fill(0)
                        }
                    bytes = Math.addExact(bytes, encrypted.size.toLong() + 4)
                    require(bytes <= MAX_FILE_BYTES)
                    output.write(length)
                    output.write(encrypted)
                }
                emit(
                    JSONObject()
                        .put("type", "metadata")
                        .put("version", 1)
                        .put("account_id", account.toString())
                        .put("created_at_ms", System.currentTimeMillis())
                )
                records(::emit)
                emit(
                    JSONObject()
                        .put("type", "end")
                        .put("record_count", validation.count)
                        .put("peer_count", validation.summary.peers)
                        .put("message_count", validation.summary.messages)
                )
                output.flush()
                raw.fd.sync()
            }
            return validation.summary
        } catch (error: Exception) {
            file.delete()
            throw error
        } finally {
            key.fill(0)
        }
    }
}
