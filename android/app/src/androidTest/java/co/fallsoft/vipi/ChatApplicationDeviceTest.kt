package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ChatApplicationDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun file(name: String) = File(context.filesDir, name)
    @Test fun prepareRealConversationUI() = runBlocking { withContext(Dispatchers.Main) {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        val config = JSONObject(file("runtime-config.json").readText()); require(config.getString("peer").startsWith("vqa_"))
        val records = PrivateRecords(context)
        val resume = InstrumentationRegistry.getArguments().getString("vipiResumeRuntime") == "true"
        // A missing backup is valid when the original app was signed out.
        // Explicit resume preserves that state rather than backing up QA login.
        if (!resume) { assertNull(records.read("runtime-session-backup")); records.read("session")?.let { records.write("runtime-session-backup", it) } }
        val session = JSONObject(file("runtime-session.json").readText()); file("runtime-session.json").delete()
        if (resume) assertEquals(session.getString("userID"), records.read("session")!!.getString("userID"))
        records.write("session", session)
        val auth = Authentication(context)
        ChatSession(context, auth, requireNotNull(auth.userID)).use { chat ->
            chat.start(); assertTrue(chat.notice, chat.ready)
            val peer = chat.find(config.getString("peer"))
            assertTrue(chat.messages(peer.id).any { !it.outgoing && it.text == "A real conversation from the iOS app coordinator — café ☕" })
            file("runtime-ready.json").writeText(JSONObject().put("run", config.getString("run")).put("received_ios_coordinator", true).toString())
        }
    } }
    @Test fun verifyDeliveryAndRestoreAfterUI() = runBlocking { withContext(Dispatchers.Main) {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        val config = JSONObject(file("runtime-config.json").readText()); val auth = Authentication(context)
        ChatSession(context, auth, requireNotNull(auth.userID)).use { chat ->
            chat.start(); assertTrue(chat.notice, chat.ready)
            val peer = chat.find(config.getString("peer"))
            assertTrue(chat.messages(peer.id).any { it.outgoing && it.text == "Coffee tomorrow? Sent from the Android conversation screen." && it.state == "delivered" })
        }
        val records = PrivateRecords(context)
        records.read("runtime-session-backup")?.let { records.write("session", it) } ?: records.remove("session")
        records.remove("runtime-session-backup"); file("runtime-config.json").delete(); file("runtime-session.json").delete()
        file("runtime-complete.json").writeText(JSONObject().put("run", config.getString("run")).put("android_ui_message_delivered", true).put("restored_session", true).toString())
    } }
}
