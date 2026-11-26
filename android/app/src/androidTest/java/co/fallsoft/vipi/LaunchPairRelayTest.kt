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
                "photo", "direct-reply", "direct-introduction", "voice", "remaining-member", "departed-member", "action-send", "action-receive", "reaction-set", "reaction-observe"))
        }
        val action = stage.startsWith("action-") || stage.startsWith("reaction-")
        val operation = if (action) "-" + requireNotNull(args.getString("operation")).also { require(it.matches(Regex("[a-z0-9-]{1,32}"))) } else ""
        val base = inst.targetContext
        val config = JSONObject(File(base.filesDir, "launch-pair.json").readText())
        val endpoint = config.getString("endpoint")
        require(URI(endpoint).let { it.scheme == "http" && it.host == "127.0.0.1" && it.port > 0 })
        val account = config.getJSONObject(role)
        MainActivityJourneyFixture("launch-pair-$role-$stage$operation", retainedToken = account.getString("storage")).use { owner ->
            val app = owner.isolated
            val receipt = JSONObject().put("role", role).put("stage", stage)
            val intent = File(app.filesDir, "launch-$stage$operation.intent")
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
                        withTimeout(15_000) {
                            while (!transport.request("GET", "/v1/people/$me/chat-features", device = device).let { it.optInt("version") == 1 && it.optString("device_id") == device.id.toString() }) delay(200)
                        }
                        receipt.put("media_capability", 1).put("group_protocol_version", 1).put("chat_features_version", 1)
                    } else {
                        val gid = UUID.fromString(args.getString("group"))
                        val peer = UUID.fromString(args.getString("peer"))
                        val friend = chat.find(config.getString("ios_profile"))
                        check(friend.id == peer)
                        groups.refresh()
                        when (stage) {
                            "action-send", "action-receive", "reaction-set", "reaction-observe" -> {
                                runActionStage(args, stage, chat, groups, gid, peer, me, receipt)
                            }
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
                            "direct-reply", "direct-introduction" -> {
                                val destination = args.getString("directPeer")?.let(UUID::fromString) ?: peer
                                if (destination != peer) check(chat.find(requireNotNull(args.getString("directProfile"))).id == destination)
                                val text = args.getString("body") ?: if (stage == "direct-introduction") "Hello from Android." else config.getString("direct_reply")
                                chat.send(text, destination)
                                chat.synchronize()
                                val sent = chat.messages(destination).single { it.outgoing && it.text == text }
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
                                    if (args.getString("targetId") != null) runActionStage(args, "reaction-observe", chat, groups, gid, peer, me, receipt)
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
    private suspend fun runActionStage(args: android.os.Bundle, stage: String, chat: ChatSession,
        groups: GroupsSession, gid: UUID, peer: UUID, me: UUID, receipt: JSONObject) {
        fun id(key: String) = UUID.fromString(requireNotNull(args.getString(key)))
        val ref = when (args.getString("scope")) {
            "direct" -> ConversationRef.Direct(peer)
            "group" -> ConversationRef.Group(gid)
            else -> error("Expected direct or group scope")
        }
        val vault = requireNotNull(chat.streakVault)
        val target = id("targetId")
        val sender = id("targetSender")
        val group = groups.group(gid)
        val ledger = ConversationReactions(vault)
        chat.synchronize()
        if (ref is ConversationRef.Group && groups.isActive(gid) && groups.heldMessages(gid).isNotEmpty()) groups.retryHeld(gid)
        val original = if (ref is ConversationRef.Direct) chat.quoteTarget(peer, target, sender)?.text
            else groups.messages(gid).singleOrNull { it.id == target && it.sender == sender && it.delivery != GroupDelivery.WITHHELD }?.text
        val excerpt = ChatFeatures.snippet(requireNotNull(original))
        val targetQuote = MessageQuote(target, sender, "text", excerpt)
        val link = "https://example.com/"
        val text = args.getString("body") ?: "See $link"
        when (stage) {
            "action-send" -> {
                // Feed a synthetic document through the same sender metadata parsing path as HTTPS.
                val html = "<html><head><title>Example site</title></head></html>"
                val snapshot = LinkSnapshot(link, requireNotNull(SenderLinkPreview.metadata(html).first))
                val features = ChatFeatures(reply = targetQuote, preview = snapshot)
                val sent = if (ref is ConversationRef.Direct) chat.sendWithFeatures(text, peer, features).also {
                    chat.synchronize()
                    check(chat.quoteTarget(peer, it, me)?.state in setOf("accepted", "delivered", "read"))
                } else {
                    val existing = groups.messages(gid).map { it.id }.toSet()
                    check(groups.send(requireNotNull(group), text, features))
                    groups.messages(gid).single { it.id !in existing && it.sender == me && it.features == features && it.delivery == GroupDelivery.ACCEPTED }.id
                }
                receipt.put("sent", sent).put("preview_title", snapshot.title)
            }
            "action-receive" -> {
                val event = id("messageId")
                val author = args.getString("eventSender")?.let(UUID::fromString) ?: peer
                val features = if (ref is ConversationRef.Direct) requireNotNull(chat.quoteTarget(peer, event, author)).let { check(!it.outgoing); it.features }
                    else groups.messages(gid).single { it.id == event && it.sender == author && it.delivery == GroupDelivery.RECEIVED }.features
                check(features.reply?.message == target && features.reply.sender == sender && features.reply.excerpt == excerpt)
                check(features.preview?.url == link && features.preview?.title == "Example site")
                receipt.put("received", event).put("target", target).put("preview_title", features.preview?.title)
            }
            "reaction-set", "reaction-observe" -> {
                val emoji = requireNotNull(args.getString("emoji")).takeUnless { it == "clear" }
                val sequence = requireNotNull(args.getString("sequence")).toInt()
                val actor = if (stage == "reaction-set") me else id("actor")
                if (stage == "reaction-set") {
                    val sent = if (ref is ConversationRef.Direct) chat.react(peer, target, sender, emoji)
                        else groups.react(requireNotNull(group), target, sender, emoji)
                    chat.synchronize()
                    receipt.put("sent", sent)
                }
                val actual = ledger.observed(ref, target, sender, actor)
                check(actual == (sequence to emoji) || sequence == 0 && actual == null) { "Expected sequence $sequence, observed ${actual?.first}" }
                check(if (ref is ConversationRef.Direct) chat.messages(peer).none { it.features.reaction != null }
                    else groups.messages(gid).none { it.features.reaction != null })
                receipt.put("sequence", sequence).put("emoji", emoji ?: JSONObject.NULL)
            }
        }
    }

}
