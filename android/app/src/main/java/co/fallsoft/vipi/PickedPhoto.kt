package co.fallsoft.vipi

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.Closeable
import java.io.File
import java.io.InputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

internal class PhotoTooLarge : IllegalArgumentException("Photo dimensions are too large")

internal fun checkPhotoDimensions(width: Int, height: Int) {
    if (width !in 1..16384 || height !in 1..16384 || width.toLong() * height > 64_000_000)
        throw PhotoTooLarge()
}

/**
 * An immutable preview of the bytes selected through the platform picker. Unlink the empty scratch
 * file before copying any data. The kernel releases the snapshot when its last descriptor closes,
 * including on process death.
 */
internal class PickedPhoto
private constructor(
    private val snapshot: ParcelFileDescriptor,
    val name: String,
    val mime: String,
    val width: Int,
    val height: Int,
    val preview: Bitmap,
) : Closeable {
    @Synchronized fun input(): InputStream = File("/proc/self/fd/${snapshot.fd}").inputStream()

    @Synchronized override fun close() = snapshot.close()

    companion object {
        suspend fun read(context: Context, uri: Uri): PickedPhoto {
            var descriptor: ParcelFileDescriptor? = null
            try {
                val result =
                    withContext(Dispatchers.IO) {
                        val temporary =
                            File.createTempFile("photo-selection-", null, context.cacheDir)
                        val fd =
                            try {
                                ParcelFileDescriptor.open(
                                        temporary,
                                        ParcelFileDescriptor.MODE_READ_WRITE,
                                    )
                                    .also { descriptor = it }
                            } finally {
                                check(temporary.delete()) { "Could not isolate the selected photo" }
                            }
                        val file = File("/proc/self/fd/${fd.fd}")
                        requireNotNull(context.contentResolver.openInputStream(uri)).use { source ->
                            file.outputStream().use { output ->
                                val buffer = ByteArray(65536)
                                var total = 0L
                                while (true) {
                                    currentCoroutineContext().ensureActive()
                                    val count = source.read(buffer)
                                    if (count < 0) break
                                    total += count
                                    require(total <= MediaCryptography.MAX_BYTES) {
                                        "Photo is too large"
                                    }
                                    output.write(buffer, 0, count)
                                }
                                require(total > 0) { "Photo is empty" }
                            }
                        }
                        var mime = ""
                        var width = 0
                        var height = 0
                        val bitmap =
                            ImageDecoder.decodeBitmap(ImageDecoder.createSource(file)) {
                                decoder,
                                info,
                                _ ->
                                mime = info.mimeType
                                width = info.size.width
                                height = info.size.height
                                require(mime.startsWith("image/")) { "Choose a supported photo" }
                                checkPhotoDimensions(width, height)
                                val scale = minOf(1.0, 512.0 / width, 512.0 / height)
                                decoder.setTargetSize(
                                    maxOf(1, (width * scale).toInt()),
                                    maxOf(1, (height * scale).toInt()),
                                )
                                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                            }
                        val name =
                            runCatching {
                                    context.contentResolver
                                        .query(
                                            uri,
                                            arrayOf(OpenableColumns.DISPLAY_NAME),
                                            null,
                                            null,
                                            null,
                                        )
                                        ?.use {
                                            if (it.moveToFirst()) it.getString(0) else null
                                        }
                                }
                                .getOrNull()
                                ?.filter { it.code >= 32 && it !in "/\\" }
                                ?.trim()
                                ?.take(255)
                                ?.takeIf(String::isNotBlank) ?: "Photo"
                        PickedPhoto(fd, name, mime, width, height, bitmap)
                    }
                descriptor = null
                return result
            } finally {
                descriptor?.close()
            }
        }
    }
}
