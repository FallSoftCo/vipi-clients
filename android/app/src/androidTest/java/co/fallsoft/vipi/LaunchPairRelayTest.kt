package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.URI
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.UUID
import kotlin.math.PI
import kotlin.math.sin

/** Each invocation advances one explicit cross-platform step. The other client supplies the group
 * and message IDs. Original intent receipts survive a crash so a sender is never replayed. */
class LaunchPairRelayTest {
    @Test fun exchangeWithNativePeer() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        assumeTrue(args.getString("vipiLaunchPair") == "true")
        val role = requireNotNull(args.getString("role")).also { require(it in setOf("android", "member")) }
        val stage = requireNotNull(args.getString("stage")).also {
            require(it in setOf("register", "accept", "bootstrap", "bootstrap-after-contact", "group-receive", "group-reply",
                "photo", "direct-reply", "voice", "remaining-member", "departed-member"))
        }
        val base = inst.targetContext
        val config = JSONObject(File(base.filesDir, "launch-pair.json").readText())
        val endpoint = config.getString("endpoint")
        require(URI(endpoint).let { it.scheme == "http" && it.host == "127.0.0.1" && it.port > 0 })
        val account = config.getJSONObject(role)
        MainActivityJourneyFixture("launch-pair-$role-$stage", retainedToken = account.getString("storage")).use { owner ->
            val app = owner.isolated
            val receipt = JSONObject().put("role", role).put("stage", stage)
            val intent = File(app.filesDir, "launch-$stage.intent")
            require(intent.createNewFile()) { "This stage was previously dispatched for this participant." }
            runBlocking { withContext(Dispatchers.Main.immediate) {
                val user = account.getString("subject")
                PrivateRecords(app).write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
                    .put("userID", user).put("accessToken", account.getString("access_token")).put("refreshToken", "loopback-fixture")))
                val transport = ServiceClient(Authentication(app), user, endpoint)
                ChatSession(app, transport, user).use { chat ->
                    chat.start()
                    if (stage == "register" && chat.needsProfile) chat.createProfile(account.getString("profile"), "Vipi QA $role")
                    check(chat.ready) { chat.notice.orEmpty() }
                    val me = requireNotNull(chat.profile).id
                    val device = requireNotNull(chat.eventDevice())
                    val groups = requireNotNull(chat.groups)
                    check(groups.remoteAvailable)
                    receipt.put("account", me).put("device", device.id)
                    if (stage == "register") {
                        withTimeout(10_000) {
                            while (transport.request("GET", "/v1/media/capability/$me", device = device).optString("device_id") != device.id.toString()) delay(200)
                        }
                        receipt.put("media_capability", 1).put("group_protocol_version", 1)
                    } else {
                        val gid = UUID.fromString(args.getString("group"))
                        val peer = UUID.fromString(args.getString("peer"))
                        val friend = chat.find(config.getString("ios_profile"))
                        check(friend.id == peer)
                        groups.refresh()
                        when (stage) {
                            "accept" -> {
                                val invite = groups.invitations.single { it.group == gid }
                                groups.answer(invite, true)
                                check(groups.notice == null && groups.group(gid) != null) { groups.notice.orEmpty() }
                                receipt.put("accepted", invite.id)
                            }
                            "bootstrap", "bootstrap-after-contact" -> {
                                chat.synchronize()
                                if (stage == "bootstrap-after-contact") {
                                    val greeting = UUID.fromString(args.getString("introductionMessage"))
                                    check(chat.messages(peer).any { it.id == greeting && !it.outgoing })
                                    check(chat.securityNumber(peer) != null)
                                    groups.retryHeld(gid)
                                    receipt.put("prior_direct_message", greeting)
                                }
                                val proposal = requireNotNull(groups.pendingApprovals(gid).singleOrNull { groups.canBootstrap(it) }) {
                                    "An inviter's pinned Signal identity and an authenticated group bootstrap control are required."
                                }
                                groups.confirmBootstrap(proposal)
                                check(groups.approved(gid, me) && groups.approved(gid, peer))
                                receipt.put("bootstrap_confirmed", gid)
                            }
                            "group-receive", "group-reply" -> {
                                chat.synchronize()
                                val remote = UUID.fromString(args.getString("groupMessage"))
                                val row = groups.messages(gid).single { it.id == remote && it.sender == peer }
                                check(row.delivery == GroupDelivery.RECEIVED && row.text == config.getString("group_in"))
                                receipt.put("received", row.id)
                                if (stage == "group-reply") {
                                    check(groups.send(requireNotNull(groups.group(gid)), config.getString("group_reply"))) { groups.notice.orEmpty() }
                                    receipt.put("sent", groups.messages(gid).single { it.sender == me && it.delivery == GroupDelivery.ACCEPTED && it.text == config.getString("group_reply") }.id)
                                }
                            }
                            "photo" -> {
                                chat.synchronize()
                                val remote = UUID.fromString(args.getString("photoMessage"))
                                val item = chat.messages(peer).single { it.id == remote && !it.outgoing }.attachments.single()
                                check(item.kind == AttachmentKind.PHOTO)
                                val file = chat.openMedia(peer, item, AttachmentRepository(app, me))
                                val hash = try { MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) } } finally { file.delete() }
                                check(hash == args.getString("photoSHA"))
                                receipt.put("opened_photo", remote).put("sha256", hash)
                            }
                            "voice" -> {
                                check(role == "android")
                                chat.requirePeerMedia(peer)
                                val source = File(app.cacheDir, "launch-tone.wav")
                                val rate = 16_000
                                val frames = rate * 12 / 10
                                val pcm = ByteBuffer.allocate(frames * 2).order(ByteOrder.LITTLE_ENDIAN)
                                repeat(frames) { i -> pcm.putShort((6_000 * sin(2 * PI * 660 * i / rate)).toInt().toShort()) }
                                PcmWave(rate, 1, pcm.array()).write(source)
                                val hash = MessageDigest.getInstance("SHA-256").digest(source.readBytes())
                                    .joinToString("") { "%02x".format(it) }
                                val drafts = requireNotNull(chat.voiceDrafts)
                                val voice = drafts.save(peer, source).await()
                                check(voice.kind == AttachmentKind.VOICE && voice.durationMillis == 1200L)
                                val sent = chat.sendVoiceDraft("Voice message", peer, voice) {}
                                chat.synchronize()
                                check(chat.messages(peer).single { it.id == sent }.state in setOf("accepted", "delivered", "read"))
                                check(drafts.current(peer) == null)
                                receipt.put("sent", sent).put("manifest", voice.id).put("sha256", hash)
                                    .put("duration_ms", voice.durationMillis).put("bytes", voice.original.plaintextBytes)
                            }
                            "direct-reply" -> {
                                val text = config.getString("direct_reply")
                                chat.send(text, peer)
                                chat.synchronize()
                                val sent = chat.messages(peer).single { it.outgoing && it.text == text }
                                check(sent.state in setOf("accepted", "delivered", "read")) { sent.state }
                                receipt.put("sent", sent.id)
                            }
                            "remaining-member", "departed-member" -> {
                                chat.synchronize()
                                val expected = UUID.fromString(args.getString("groupMessage"))
                                val messages = groups.messages(gid)
                                if (stage == "remaining-member") {
                                    check(groups.isActive(gid))
                                    check(messages.single { it.id == expected && it.sender == peer }.let {
                                        it.delivery == GroupDelivery.RECEIVED && it.text == config.getString("after_removal")
                                    })
                                } else {
                                    check(!groups.isActive(gid) && groups.departedGroups.any { it.id == gid })
                                    check(messages.none { it.id == expected })
                                }
                                receipt.put("message", expected).put("active", groups.isActive(gid))
                            }
                            else -> error("Unknown controlled exchange stage")
                        }
                    }
                }
            } }
            File(owner.output, "receipt.json").writeText(receipt.toString(2))
        }
    }
}
