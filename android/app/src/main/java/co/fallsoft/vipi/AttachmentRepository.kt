package co.fallsoft.vipi

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.UUID

/** Private durable ciphertext and explicitly requested verified playback files.
 * Callers commit a prepared manifest into the encrypted draft before networking. */
internal class AttachmentRepository(private val context: Context, val account: UUID, preview: Boolean = false) {
    companion object {
        private val process = UUID.randomUUID().toString()
        private val cleaned = mutableSetOf<String>()
    }
    private val root = if (preview) {
        val parent = File(context.cacheDir, "attachment-previews/$account").apply { check(isDirectory || mkdirs()) }
        parent.listFiles()?.filter { !it.name.startsWith(process) }?.forEach { it.deleteRecursively() }
        File(parent, "$process-${UUID.randomUUID()}").apply { check(mkdir()) }
    } else File(context.noBackupFilesDir, "attachments/$account").apply { check(isDirectory || mkdirs()) }
    private val verified = File(context.cacheDir, "attachments/$account").also { directory ->
        check(directory.isDirectory || directory.mkdirs())
        synchronized(cleaned) {
            if (cleaned.add(directory.canonicalPath)) directory.listFiles()?.forEach { it.delete() }
        }
    }
    fun ciphertext(part: MediaPart): File = File(root, "${part.blobId}.ciphertext")
    private fun filename(uri: Uri, fallback: String): String = runCatching {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }.getOrNull()?.filter { it.code >= 32 && it !in "/\\" }?.trim()?.take(255)?.takeIf { it.isNotBlank() } ?: fallback

    suspend fun prepare(uri: Uri, kind: AttachmentKind): AttachmentManifest = withContext(Dispatchers.IO) {
        require(kind in setOf(AttachmentKind.PHOTO, AttachmentKind.VIDEO, AttachmentKind.VOICE))
        val execution = currentCoroutineContext()
        val id = UUID.randomUUID(); val key = MediaCryptography.freshKey(); val created = mutableListOf<File>()
        val clear = File.createTempFile("inspect-", ".private", verified)
        try {
            val (original, originalFile) = requireNotNull(context.contentResolver.openInputStream(uri)).use {
                MediaCryptography.seal(it, root, key, id, "original", checkCancelled = { execution.ensureActive() })
            }
            created += originalFile
            // Inspect the exact authenticated original, not a second provider read.
            MediaCryptography.open(originalFile, clear, key, id, original) { execution.ensureActive() }
            var width: Int? = null; var height: Int? = null; var duration: Long? = null
            var contentType = ""; var image: Bitmap? = null
            if (kind == AttachmentKind.PHOTO) {
                image = ImageDecoder.decodeBitmap(ImageDecoder.createSource(clear)) { decoder, info, _ ->
                    checkPhotoDimensions(info.size.width, info.size.height)
                    width = info.size.width; height = info.size.height; contentType = info.mimeType
                    require(contentType.startsWith("image/")) { "Choose a supported photo" }
                    val ratio = minOf(1.0, 256.0 / info.size.width, 256.0 / info.size.height)
                    decoder.setTargetSize(maxOf(1, (info.size.width * ratio).toInt()), maxOf(1, (info.size.height * ratio).toInt()))
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                }
            } else {
                val reader = MediaMetadataRetriever()
                try {
                    reader.setDataSource(clear.path)
                    duration = reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
                    require(duration != null && duration!! in 1..180000) { "Choose media shorter than three minutes" }
                    contentType = reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_MIMETYPE).orEmpty()
                    if (kind == AttachmentKind.VIDEO) {
                        require(reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO) == "yes" && contentType.startsWith("video/")) { "Choose a supported video" }
                        width = reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull()
                        height = reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull()
                        require(width != null && height != null && width!! in 1..16384 && height!! in 1..16384)
                        val ratio = minOf(1.0, 256.0 / width!!, 256.0 / height!!)
                        image = reader.getScaledFrameAtTime(0, MediaMetadataRetriever.OPTION_CLOSEST_SYNC,
                            maxOf(1, (width!! * ratio).toInt()), maxOf(1, (height!! * ratio).toInt()))
                        require(image != null) { "Video preview is unavailable" }
                    } else {
                        require(reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_AUDIO) == "yes" &&
                            reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO) != "yes" &&
                            (contentType.startsWith("audio/") || contentType == "video/mp4")) { "Choose a supported voice recording" }
                    }
                } finally { reader.release() }
            }
            val thumbnail = image?.let { bitmap ->
                try {
                    val bytes = ByteArrayOutputStream().use { output ->
                        require(bitmap.compress(Bitmap.CompressFormat.JPEG, 80, output)); output.toByteArray()
                    }
                    MediaCryptography.seal(ByteArrayInputStream(bytes), root, key, id, "thumbnail", 512 * 1024) { execution.ensureActive() }.also { created += it.second }.first
                } finally { bitmap.recycle() }
            }
            execution.ensureActive()
            AttachmentManifest(id, kind, key, original, thumbnail,
                filename(uri, if (kind == AttachmentKind.PHOTO) "Photo" else if (kind == AttachmentKind.VIDEO) "Video" else "Voice message.m4a"),
                contentType, width, height, duration).also { it.validate() }
        } catch (error: Exception) {
            created.forEach(File::delete)
            throw error
        } finally { clear.delete() }
    }

    /** Ownership passes to the encrypted outbox at its transaction commit. If
     * selection, compression, queueing or a dispatcher handoff is cancelled
     * before then, remove only these newly created ciphertext files. */
    suspend fun commitPickedPhoto(photo: PickedPhoto, enqueue: (AttachmentManifest, () -> Unit) -> Unit) {
        val files = mutableListOf<File>()
        var committed = false
        try {
            val manifest = withContext(Dispatchers.IO) {
                val execution = currentCoroutineContext()
                val id = UUID.randomUUID()
                val key = MediaCryptography.freshKey()
                val original = photo.input().use {
                    MediaCryptography.seal(it, root, key, id, "original", checkCancelled = { execution.ensureActive() })
                }.also { files += it.second }.first
                val scale = minOf(1.0, 256.0 / photo.preview.width, 256.0 / photo.preview.height)
                val thumb = Bitmap.createScaledBitmap(photo.preview, maxOf(1, (photo.preview.width * scale).toInt()),
                    maxOf(1, (photo.preview.height * scale).toInt()), true)
                val jpeg = try {
                    ByteArrayOutputStream().use { output ->
                        check(thumb.compress(Bitmap.CompressFormat.JPEG, 80, output))
                        output.toByteArray()
                    }
                } finally { if (thumb !== photo.preview) thumb.recycle() }
                val thumbnail = try {
                    MediaCryptography.seal(ByteArrayInputStream(jpeg), root, key, id, "thumbnail", 512 * 1024) {
                        execution.ensureActive()
                    }.also { files += it.second }.first
                } finally { jpeg.fill(0) }
                AttachmentManifest(id, AttachmentKind.PHOTO, key, original, thumbnail, photo.name,
                    photo.mime, photo.width, photo.height, null).also { it.validate() }
            }
            enqueue(manifest) { committed = true }
            check(committed) { "Photo was not queued" }
        } finally {
            if (!committed) files.forEach(File::delete)
        }
    }

    fun newPreview() = AttachmentRepository(context, account, preview = true)
    fun closePreview() {
        val parent = File(context.cacheDir, "attachment-previews/$account")
        check(root.parentFile == parent && root.name.startsWith("$process-"))
        root.deleteRecursively()
    }

    /** Copies only sealed preview bytes. The durable journal commit transfers ownership. */
    suspend fun adopt(preview: AttachmentRepository, manifest: AttachmentManifest,
                      enqueue: suspend (() -> Unit) -> Unit) {
        require(account == preview.account)
        val created = mutableListOf<File>()
        var committed = false
        try {
            withContext(Dispatchers.IO) {
                for (part in listOfNotNull(manifest.original, manifest.thumbnail)) {
                    val target = ciphertext(part)
                    check(!target.exists())
                    val temporary = File.createTempFile("adopt-", ".partial", root)
                    try {
                        preview.ciphertext(part).inputStream().use { input ->
                            java.io.FileOutputStream(temporary).use { output -> input.copyTo(output); output.fd.sync() }
                        }
                        check(temporary.length() == part.ciphertextBytes)
                        MediaCryptography.publish(temporary, target)
                        created += target
                    } finally { temporary.delete() }
                }
            }
            enqueue { committed = true }
        } finally { if (!committed) created.forEach(File::delete) }
    }

    fun discard(manifest: AttachmentManifest) {
        listOfNotNull(manifest.original, manifest.thumbnail).forEach { ciphertext(it).delete() }
    }

    suspend fun openLocal(manifest: AttachmentManifest): File = withContext(Dispatchers.IO) {
        val execution = currentCoroutineContext()
        val output = File.createTempFile("play-", ".verified", verified)
        try {
            MediaCryptography.open(ciphertext(manifest.original), output, manifest.key, manifest.id, manifest.original) { execution.ensureActive() }
        } catch (failure: Exception) { output.delete(); throw failure }
    }

    suspend fun localPhotoThumbnail(manifest: AttachmentManifest): Bitmap? = withContext(Dispatchers.IO) {
        val part = manifest.thumbnail ?: return@withContext null
        val file = ciphertext(part)
        if (!file.isFile) return@withContext null
        val execution = currentCoroutineContext()
        val jpeg = MediaCryptography.thumbnailBytes(file, manifest) { execution.ensureActive() }
        try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(java.nio.ByteBuffer.wrap(jpeg))) { decoder, info, _ ->
                require(info.size.width in 1..256 && info.size.height in 1..256)
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            }
        } finally { jpeg.fill(0) }
    }

    suspend fun ensureUploaded(manifest: AttachmentManifest, api: ChatTransport, bytes: CiphertextTransport, device: DeviceCredential) {
        manifest.validate()
        for (part in listOfNotNull(manifest.original, manifest.thumbnail)) {
            val response = api.request("POST", "/v1/media/uploads", JSONObject().put("id", part.blobId)
                .put("ciphertext_bytes", part.ciphertextBytes).put("ciphertext_sha256", part.ciphertextSHA256), device)
            require(response.getString("id") == part.blobId.toString() && response.getLong("ciphertext_bytes") == part.ciphertextBytes &&
                response.getString("ciphertext_sha256") == part.ciphertextSHA256)
            when (response.getString("state")) {
                "ready" -> Unit
                "uploading" -> bytes.upload(part, ciphertext(part), device)
                else -> throw ServiceFailure(404, "media_unavailable")
            }
        }
    }
    suspend fun open(manifest: AttachmentManifest, thumbnail: Boolean, bytes: CiphertextTransport, device: DeviceCredential): File {
        manifest.validate()
        val part = if (thumbnail) requireNotNull(manifest.thumbnail) else manifest.original
        val source = obtainCiphertext(part, bytes, device)
        return withContext(Dispatchers.IO) {
            val execution = currentCoroutineContext()
            MediaCryptography.open(source, File(verified, "${manifest.id}.${part.role}.verified"), manifest.key, manifest.id, part) {
                execution.ensureActive()
            }
        }
    }

    suspend fun viewPhoto(manifest: AttachmentManifest, bytes: CiphertextTransport, device: DeviceCredential): Bitmap {
        manifest.validate()
        require(manifest.kind == AttachmentKind.PHOTO)
        val source = obtainCiphertext(manifest.original, bytes, device)
        return withContext(Dispatchers.IO) {
            val execution = currentCoroutineContext()
            MediaCryptography.readOriginal(source, verified, manifest, { execution.ensureActive() }) { file ->
                ImageDecoder.decodeBitmap(ImageDecoder.createSource(file)) { decoder, info, _ ->
                    val size = info.size
                    require(info.mimeType.startsWith("image/"))
                    checkPhotoDimensions(size.width, size.height)
                    val scale = minOf(1.0, 1536.0 / maxOf(size.width, size.height))
                    decoder.setTargetSize(maxOf(1, (size.width * scale).toInt()), maxOf(1, (size.height * scale).toInt()))
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                }
            }
        }
    }

    private suspend fun obtainCiphertext(part: MediaPart, bytes: CiphertextTransport, device: DeviceCredential): File {
        val source = ciphertext(part)
        val complete = withContext(Dispatchers.IO) {
            source.isFile && source.length() == part.ciphertextBytes && source.inputStream().use { input ->
                val digest = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536)
                while (true) {
                    currentCoroutineContext().ensureActive()
                    val count = input.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
                digest.digest().joinToString("") { "%02x".format(it) } == part.ciphertextSHA256
            }
        }
        return if (complete) source else bytes.download(part, source, device)
    }
    suspend fun cancelUnsent(manifest: AttachmentManifest, api: ChatTransport, device: DeviceCredential) {
        manifest.validate()
        for (part in listOfNotNull(manifest.original, manifest.thumbnail)) {
            require(api.request("DELETE", "/v1/media/uploads/${part.blobId}", device = device).getBoolean("cancelled"))
        }
    }
}
