package co.fallsoft.vipi

import android.system.Os
import android.system.OsConstants
import android.util.Base64
import java.io.DataInputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Locale
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject

internal enum class AttachmentKind {
    PHOTO,
    VIDEO,
    VOICE,
    FILE,
}

internal data class MediaPart(
    val blobId: UUID,
    val role: String,
    val plaintextBytes: Long,
    val ciphertextBytes: Long,
    val ciphertextSHA256: String,
) {
    fun json() =
        JSONObject()
            .put("blob_id", blobId.toString())
            .put("role", role)
            .put("plaintext_bytes", plaintextBytes)
            .put("ciphertext_bytes", ciphertextBytes)
            .put("ciphertext_sha256", ciphertextSHA256)

    fun validate(maxBytes: Long = MediaCryptography.MAX_BYTES) {
        require(role in setOf("original", "thumbnail") && plaintextBytes in 1..maxBytes)
        require(
            ciphertextBytes == plaintextBytes + 28 &&
                ciphertextSHA256.matches(Regex("[a-f0-9]{64}"))
        )
    }

    companion object {
        fun parse(v: JSONObject) =
            MediaPart(
                    UUID.fromString(v.getString("blob_id")),
                    v.getString("role"),
                    v.getLong("plaintext_bytes"),
                    v.getLong("ciphertext_bytes"),
                    v.getString("ciphertext_sha256"),
                )
                .also { it.validate() }
    }
}

/** This manifest is stored only in MessageVault / inside the Signal payload. */
internal data class AttachmentManifest(
    val id: UUID,
    val kind: AttachmentKind,
    val key: ByteArray,
    val original: MediaPart,
    val thumbnail: MediaPart?,
    val filename: String,
    val contentType: String,
    val width: Int? = null,
    val height: Int? = null,
    val durationMillis: Long? = null,
) {
    fun validate() {
        require(
            key.size == 32 &&
                filename.isNotBlank() &&
                filename.length <= 255 &&
                filename.none { it.code < 32 }
        )
        require(contentType.length in 1..127 && original.role == "original")
        require(thumbnail == null || thumbnail.blobId != original.blobId)
        original.validate()
        thumbnail?.let {
            require(it.role == "thumbnail")
            it.validate(512 * 1024)
        }
        require(width == null || width in 1..16384)
        require(height == null || height in 1..16384)
        require(durationMillis == null || durationMillis in 1..180000)
    }

    override fun equals(other: Any?): Boolean =
        other is AttachmentManifest &&
            id == other.id &&
            kind == other.kind &&
            key.contentEquals(other.key) &&
            original == other.original &&
            thumbnail == other.thumbnail &&
            filename == other.filename &&
            contentType == other.contentType &&
            width == other.width &&
            height == other.height &&
            durationMillis == other.durationMillis

    override fun hashCode(): Int = 31 * id.hashCode() + key.contentHashCode()

    fun json() =
        JSONObject()
            .put("version", 1)
            .put("id", id.toString())
            .put("kind", kind.name.lowercase(Locale.ROOT))
            .put("key", Base64.encodeToString(key, Base64.NO_WRAP))
            .put("original", original.json())
            .put("thumbnail", thumbnail?.json())
            .put("filename", filename)
            .put("content_type", contentType)
            .put("width", width)
            .put("height", height)
            .put("duration_ms", durationMillis)

    val blobIds
        get() = listOfNotNull(original.blobId, thumbnail?.blobId)

    companion object {
        fun parse(v: JSONObject): AttachmentManifest {
            require(v.getInt("version") == 1)
            return AttachmentManifest(
                    UUID.fromString(v.getString("id")),
                    AttachmentKind.valueOf(v.getString("kind").uppercase(Locale.ROOT)),
                    Base64.decode(v.getString("key"), Base64.NO_WRAP),
                    MediaPart.parse(v.getJSONObject("original")),
                    v.optJSONObject("thumbnail")?.let(MediaPart::parse),
                    v.getString("filename"),
                    v.getString("content_type"),
                    if (v.has("width") && !v.isNull("width")) v.getInt("width") else null,
                    if (v.has("height") && !v.isNull("height")) v.getInt("height") else null,
                    if (v.has("duration_ms") && !v.isNull("duration_ms")) v.getLong("duration_ms")
                    else null,
                )
                .also { it.validate() }
        }
    }
}

/**
 * Standard platform AES-256-GCM. File format:12-byte nonce | ciphertext |16-byte tag. Streaming
 * plaintext is kept in a PRIVATE temporary file during decrypt and is never published until
 * doFinal() authenticates the entire file and AAD.
 */
internal object MediaCryptography {
    const val MAX_BYTES = 32 * 1024 * 1024L
    private val random = SecureRandom()

    fun freshKey() = ByteArray(32).also(random::nextBytes)

    private fun aad(id: UUID, role: String) =
        "vipi-attachment-v1\u0000$id\u0000$role".toByteArray(Charsets.UTF_8)

    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }

    internal fun publish(temporary: File, destination: File) {
        Files.move(
            temporary.toPath(),
            destination.toPath(),
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING,
        )
        val descriptor =
            Os.open(requireNotNull(destination.parentFile).path, OsConstants.O_RDONLY, 0)
        try {
            Os.fsync(descriptor)
        } finally {
            Os.close(descriptor)
        }
    }

    @Synchronized
    fun seal(
        input: InputStream,
        directory: File,
        key: ByteArray,
        attachment: UUID,
        role: String,
        maxBytes: Long = MAX_BYTES,
        checkCancelled: () -> Unit = {},
    ): Pair<MediaPart, File> {
        require(
            key.size == 32 && role in setOf("original", "thumbnail") && maxBytes in 1..MAX_BYTES
        )
        require(directory.isDirectory || directory.mkdirs())
        val blob = UUID.randomUUID()
        val temporary = File.createTempFile("media-", ".partial", directory)
        val destination = File(directory, "$blob.ciphertext")
        val nonce = ByteArray(12).also(random::nextBytes)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
        cipher.updateAAD(aad(attachment, role))
        val digest = MessageDigest.getInstance("SHA-256")
        var count = 0L
        try {
            FileOutputStream(temporary).use { output ->
                fun write(bytes: ByteArray) {
                    output.write(bytes)
                    digest.update(bytes)
                }
                write(nonce)
                val buffer = ByteArray(65536)
                while (true) {
                    checkCancelled()
                    val size = input.read(buffer)
                    if (size < 0) break
                    count += size
                    require(count <= maxBytes) { "Attachment is too large" }
                    cipher.update(buffer, 0, size)?.let(::write)
                }
                require(count > 0) { "Attachment is empty" }
                write(cipher.doFinal())
                output.flush()
                output.fd.sync()
            }
            checkCancelled()
            publish(temporary, destination)
            return MediaPart(blob, role, count, destination.length(), hex(digest.digest())).also {
                it.validate(maxBytes)
            } to destination
        } finally {
            temporary.delete()
        }
    }

    @Synchronized
    private fun decrypt(
        source: File,
        output: java.io.OutputStream,
        key: ByteArray,
        attachment: UUID,
        part: MediaPart,
        checkCancelled: () -> Unit,
    ) {
        part.validate()
        require(key.size == 32 && source.length() == part.ciphertextBytes)
        val digest = MessageDigest.getInstance("SHA-256")
        var count = 0L
        FileInputStream(source).use { input ->
            val nonce = ByteArray(12)
            DataInputStream(input).readFully(nonce)
            digest.update(nonce)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(key, "AES"),
                GCMParameterSpec(128, nonce),
            )
            cipher.updateAAD(aad(attachment, part.role))
            val buffer = ByteArray(65536)
            while (true) {
                checkCancelled()
                val size = input.read(buffer)
                if (size < 0) break
                digest.update(buffer, 0, size)
                cipher.update(buffer, 0, size)?.let {
                    count += it.size
                    require(count <= part.plaintextBytes)
                    output.write(it)
                }
            }
            val last = cipher.doFinal()
            count += last.size
            require(count == part.plaintextBytes && hex(digest.digest()) == part.ciphertextSHA256) {
                "Attachment authentication failed"
            }
            output.write(last)
        }
        checkCancelled()
    }

    /**
     * The only clear bytes used for display live behind an unlinked descriptor. The reader is
     * invoked only after the GCM tag and manifest digest match.
     */
    fun <T> readOriginal(
        source: File,
        scratch: File,
        manifest: AttachmentManifest,
        checkCancelled: () -> Unit,
        read: (File) -> T,
    ): T {
        val temporary = File.createTempFile("photo-view-", ".private", scratch)
        try {
            android.os.ParcelFileDescriptor.open(
                    temporary,
                    android.os.ParcelFileDescriptor.MODE_READ_WRITE,
                )
                .use { fd ->
                    check(temporary.delete())
                    val privateFile = File("/proc/self/fd/${fd.fd}")
                    privateFile.outputStream().use {
                        decrypt(
                            source,
                            it,
                            manifest.key,
                            manifest.id,
                            manifest.original,
                            checkCancelled,
                        )
                    }
                    return read(privateFile)
                }
        } finally {
            temporary.delete()
        }
    }

    fun thumbnailBytes(
        source: File,
        manifest: AttachmentManifest,
        checkCancelled: () -> Unit,
    ): ByteArray {
        val part = requireNotNull(manifest.thumbnail)
        part.validate(512 * 1024L)
        return java.io.ByteArrayOutputStream(part.plaintextBytes.toInt()).use { output ->
            decrypt(source, output, manifest.key, manifest.id, part, checkCancelled)
            output.toByteArray()
        }
    }

    fun open(
        source: File,
        destination: File,
        key: ByteArray,
        attachment: UUID,
        part: MediaPart,
        checkCancelled: () -> Unit = {},
    ): File {
        require(destination.parentFile?.isDirectory == true)
        val temporary = File.createTempFile("verified-media-", ".partial", destination.parentFile)
        try {
            FileOutputStream(temporary).use { output ->
                decrypt(source, output, key, attachment, part, checkCancelled)
                output.flush()
                output.fd.sync()
            }
            checkCancelled()
            publish(temporary, destination)
            return destination
        } finally {
            temporary.delete()
        }
    }
}

/** Validate the authenticated message list before any journal write or receipt. */
internal object MessageAttachments {
    fun validate(values: List<AttachmentManifest>) {
        require(values.size <= 4)
        values.forEach(AttachmentManifest::validate)
        require(values.map { it.id }.distinct().size == values.size)
        val blobs = values.flatMap { it.blobIds }
        require(blobs.size <= 8 && blobs.distinct().size == blobs.size)
    }

    fun json(values: List<AttachmentManifest>) =
        org.json.JSONArray().also { array ->
            validate(values)
            values.forEach { array.put(it.json()) }
        }

    fun parse(value: JSONObject): List<AttachmentManifest> {
        if (!value.has("attachments")) return emptyList()
        val array = value.getJSONArray("attachments")
        require(array.length() <= 4)
        return (0 until array.length())
            .map { AttachmentManifest.parse(array.getJSONObject(it)) }
            .also(::validate)
    }
}
