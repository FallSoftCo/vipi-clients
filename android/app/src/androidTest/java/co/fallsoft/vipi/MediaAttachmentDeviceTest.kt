package co.fallsoft.vipi

import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real platform AES-GCM, libsignal and encrypted journals. HTTP transport is separately qualified;
 * this does not claim a cross-platform or picker test.
 */
@RunWith(AndroidJUnit4::class)
class MediaAttachmentDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun reject(action: () -> Unit) = assertTrue(runCatching(action).isFailure)

    private fun photo(size: Int): ByteArray {
        val image = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        image.eraseColor(0xffd77566.toInt())
        return ByteArrayOutputStream().use { output ->
            check(image.compress(Bitmap.CompressFormat.JPEG, 90, output))
            image.recycle()
            output.toByteArray()
        }
    }

    @Test
    fun photoKeyTravelsInsideSignalAndSurvivesOfflineJournalRetry() {
        val directory =
            File(context.filesDir, "media-qa-${UUID.randomUUID()}").also { check(it.mkdir()) }
        val alice = UUID.randomUUID()
        val bob = UUID.randomUUID()
        val now = System.currentTimeMillis()
        val id = UUID.randomUUID()
        val attachment = UUID.randomUUID()
        val key = MediaCryptography.freshKey()
        val originalBytes = photo(96)
        val thumbnailBytes = photo(24)
        try {
            val (original, originalFile) =
                MediaCryptography.seal(
                    ByteArrayInputStream(originalBytes),
                    directory,
                    key,
                    attachment,
                    "original",
                )
            val (thumbnail, thumbnailFile) =
                MediaCryptography.seal(
                    ByteArrayInputStream(thumbnailBytes),
                    directory,
                    key,
                    attachment,
                    "thumbnail",
                    512 * 1024,
                )
            val manifest =
                AttachmentManifest(
                    attachment,
                    AttachmentKind.PHOTO,
                    key,
                    original,
                    thumbnail,
                    "qa-photo.jpg",
                    "image/jpeg",
                    96,
                    96,
                )
            val routed =
                MessageVault(context, bob).use { bobVault ->
                    val remote = MessagingCore(bobVault)
                    val publication = remote.keys.publication(now, 1)
                    val request = UUID.randomUUID()
                    val response =
                        JSONObject()
                            .put("request_id", request)
                            .put("user_id", bob)
                            .put("device_id", remote.device.id)
                            .put("signal_device_id", 1)
                            .put("registration_id", publication.getInt("registration_id"))
                            .put("identity_key", publication.getString("identity_key"))
                            .put("signed", publication.getJSONObject("signed"))
                            .put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
                    MessageVault(context, alice).use { vault ->
                        val core = MessagingCore(vault)
                        core.keys.establish(bob, request, response)
                        vault.transaction {
                            vault.storeAvatar(alice, ProfileAvatar(now, originalBytes))
                        }
                        core.journal.saveDraft(
                            id,
                            bob,
                            "Photo",
                            now,
                            now,
                            attachments = listOf(manifest),
                        )
                    }
                    // Reopen before encryption, exactly as an offline draft resumes.
                    MessageVault(context, alice).use { vault ->
                        val core = MessagingCore(vault)
                        val draft = requireNotNull(core.journal.draft(id))
                        core.queue(id, bob, draft.text, draft.createdAt, now, draft.attachments)
                    }
                }
            val outer = routed.sendJSON()
            assertFalse(outer.has("key"))
            assertFalse(outer.has("filename"))
            assertFalse(outer.has("content_type"))
            assertEquals(
                listOf(original.blobId.toString(), thumbnail.blobId.toString()),
                (0 until outer.getJSONArray("attachment_ids").length()).map {
                    outer.getJSONArray("attachment_ids").getString(it)
                },
            )
            MessageVault(context, alice).use { vault ->
                val core = MessagingCore(vault)
                val saved = requireNotNull(core.journal.outgoing(id))
                val retried = core.queue(id, bob, "Photo", now, now, saved.attachments)
                assertArrayEquals(routed.envelope.ciphertext, retried.envelope.ciphertext)
                assertEquals(routed.attachmentIds, retried.attachmentIds)
                reject {
                    core.queue(
                        id,
                        bob,
                        "Photo",
                        now,
                        now,
                        listOf(manifest.copy(key = MediaCryptography.freshKey())),
                    )
                }
            }
            MessageVault(context, bob).use { vault ->
                val core = MessagingCore(vault)
                val received = core.receive(routed, now)
                assertEquals(listOf(manifest), received.attachments)
                assertFalse(outer.has("profile_avatar"))
                val avatar = requireNotNull(vault.transaction { vault.avatar(alice) })
                assertEquals(now, avatar.revision)
                assertArrayEquals(originalBytes, avatar.jpeg)
                assertEquals(listOf(manifest), core.receive(routed, now).attachments)
                val parsed = received.attachments.single()
                val clear = File(directory, "verified-original.jpg")
                MediaCryptography.open(originalFile, clear, parsed.key, parsed.id, parsed.original)
                assertArrayEquals(originalBytes, clear.readBytes())
                val thumb = File(directory, "verified-thumbnail.jpg")
                MediaCryptography.open(
                    thumbnailFile,
                    thumb,
                    parsed.key,
                    parsed.id,
                    requireNotNull(parsed.thumbnail),
                )
                assertArrayEquals(thumbnailBytes, thumb.readBytes())
            }
        } finally {
            directory.deleteRecursively()
            // Only the two freshly generated synthetic identities from this test.
            val store = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            for (account in listOf(alice, bob)) {
                File(context.noBackupFilesDir, "messages/$account").deleteRecursively()
                store.deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }

    @Test
    fun avatarTombstoneOrderingBudgetAndDeviceScopedDelivery() {
        val alice = UUID.randomUUID()
        val bob = UUID.randomUUID()
        val device = UUID.randomUUID()
        val first = ProfileAvatar(100, photo(96))
        try {
            MessageVault(context, alice).use { vault ->
                vault.transaction {
                    vault.put("peer-device", bob.toString(), device.toString().toByteArray())
                    vault.storeAvatar(alice, first)
                    val id = UUID.randomUUID()
                    val large = JSONObject().put("text", "x".repeat(59_900))
                    vault.attachOwnAvatar(large, bob, id)
                    assertFalse(large.has("profile_avatar"))
                    assertNull(vault.get("avatar-outgoing", id.toString()))
                    val payload = JSONObject()
                    vault.attachOwnAvatar(payload, bob, id)
                    assertEquals(100, payload.getJSONObject("profile_avatar").getLong("revision"))
                    vault.avatarStatus(id, "delivered")
                    val after = JSONObject()
                    vault.attachOwnAvatar(after, bob, UUID.randomUUID())
                    assertFalse(after.has("profile_avatar"))
                    vault.put(
                        "peer-device",
                        bob.toString(),
                        UUID.randomUUID().toString().toByteArray(),
                    )
                    vault.attachOwnAvatar(after, bob, UUID.randomUUID())
                    assertTrue(after.has("profile_avatar"))
                    vault.storeAvatar(alice, ProfileAvatar(101, null))
                    val removal = JSONObject()
                    vault.attachOwnAvatar(removal, bob, UUID.randomUUID())
                    assertTrue(removal.getJSONObject("profile_avatar").isNull("jpeg"))
                }
            }
            assertNull(ProfileAvatar.parse(JSONObject().put("revision", 2)))
            assertNull(
                ProfileAvatar.parse(JSONObject().put("revision", -1).put("jpeg", JSONObject.NULL))
            )
            assertNull(ProfileAvatar.parse(ProfileAvatar(101, photo(24)).json()))
            assertNull(ProfileAvatar.parse(JSONObject().put("revision", 101).put("jpeg", "AAAA")))
        } finally {
            File(context.noBackupFilesDir, "messages/$alice").deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$alice")
            }
        }
    }

    @Test
    fun photoViewerDecodesOnlyAfterAuthenticationAndNeverLeavesPlaintext() {
        val directory =
            File(context.cacheDir, "photo-viewer-${UUID.randomUUID()}").also { check(it.mkdir()) }
        try {
            val bytes = photo(20)
            val key = MediaCryptography.freshKey()
            val id = UUID.randomUUID()
            val (part, ciphertext) =
                MediaCryptography.seal(bytes.inputStream(), directory, key, id, "original")
            val manifest =
                AttachmentManifest(
                    id,
                    AttachmentKind.PHOTO,
                    key,
                    part,
                    null,
                    "photo.jpg",
                    "image/jpeg",
                    20,
                    20,
                )
            fun assertCiphertextOnly() =
                assertEquals(listOf(ciphertext.name), directory.list().orEmpty().toList())
            var decoderCalls = 0
            fun decode(file: File) {
                decoderCalls++
                assertCiphertextOnly()
                assertArrayEquals(bytes, file.readBytes())
            }
            reject {
                MediaCryptography.readOriginal(
                    ciphertext,
                    directory,
                    manifest.copy(key = MediaCryptography.freshKey()),
                    {},
                    ::decode,
                )
            }
            assertCiphertextOnly()
            reject {
                MediaCryptography.readOriginal(
                    ciphertext,
                    directory,
                    manifest,
                    { error("cancelled") },
                    ::decode,
                )
            }
            assertEquals(0, decoderCalls)
            MediaCryptography.readOriginal(ciphertext, directory, manifest, {}, ::decode)
            assertEquals(1, decoderCalls)
            assertCiphertextOnly()
            checkPhotoDimensions(8000, 8000)
            reject { checkPhotoDimensions(8000, 8001) }
            reject { checkPhotoDimensions(16385, 1) }
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun corruptWrongContextAndCancelledDecryptNeverPublishPlaintext() {
        val directory =
            File(context.filesDir, "media-qa-${UUID.randomUUID()}").also { check(it.mkdir()) }
        try {
            val key = MediaCryptography.freshKey()
            val attachment = UUID.randomUUID()
            val (part, source) =
                MediaCryptography.seal(
                    ByteArrayInputStream(photo(32)),
                    directory,
                    key,
                    attachment,
                    "original",
                )
            val target = File(directory, "verified.jpg")
            reject { MediaCryptography.open(source, target, key, UUID.randomUUID(), part) }
            assertFalse(target.exists())
            reject {
                MediaCryptography.open(
                    source,
                    target,
                    key,
                    attachment,
                    part.copy(role = "thumbnail"),
                )
            }
            assertFalse(target.exists())
            reject {
                MediaCryptography.open(source, target, key, attachment, part) {
                    error("cancelled by owner")
                }
            }
            assertFalse(target.exists())
            val bytes = source.readBytes()
            bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte()
            source.writeBytes(bytes)
            reject { MediaCryptography.open(source, target, key, attachment, part) }
            assertFalse(target.exists())
            assertFalse(directory.listFiles().orEmpty().any { it.name.endsWith(".partial") })
        } finally {
            directory.deleteRecursively()
        }
    }
}
