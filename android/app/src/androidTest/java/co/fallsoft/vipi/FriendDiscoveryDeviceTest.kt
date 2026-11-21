package co.fallsoft.vipi

import android.Manifest
import android.content.ContentProviderOperation
import android.content.ContentUris
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.ContactsContract
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.util.UUID
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class FriendDiscoveryDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun savedChatAndPrivateAddressedInvites() {
        require(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        val service = JourneyServices(profileRequired = false, peerDisplayName = "Maya")
        val hidden = UUID.randomUUID()
        MainActivityJourneyFixture("friend-discovery", { app ->
            MessageVault(app, service.account).use { vault ->
                ConversationHistory(vault)
                vault.transaction {
                    val people = (1..45).map { ChatProfile(UUID.randomUUID(), "friend_$it", "Friend $it") } +
                        listOf(ChatProfile(service.peer, "maya_music", "Maya Torres"), ChatProfile(hidden, "hidden_user", "Blocked Person"),
                            ChatProfile(service.account, "myself", "Self Person"))
                    people.forEach { vault.put("contact", it.id.toString(), it.json().toString().toByteArray()) }
                    vault.put("blocked", hidden.toString(), byteArrayOf(1))
                    val now = System.currentTimeMillis()
                    val envelope = ChatEnvelope(UUID.randomUUID(), service.peer, service.account, now, 1, byteArrayOf(1))
                    vault.put("incoming", envelope.id.toString(), StoredChat(envelope, "See you Saturday", "delivered", true).encode())
                    ConversationHistory.record(vault, "incoming", envelope.id, service.peer, now)
                }
            }
            service.model(app)
        }).use { f ->
            val base = f.base
            val name = "Sam Test Invite"
            val phone = "+12025550127"
            val email = "sam@example.invalid"
            val automation = f.instrumentation.uiAutomation
            val resolver = base.contentResolver
            fun <T> contactsSetup(block: () -> T): T {
                automation.adoptShellPermissionIdentity(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS)
                try { return block() } finally { automation.dropShellPermissionIdentity() }
            }
            val id = contactsSetup {
                val ops = arrayListOf(ContentProviderOperation.newInsert(ContactsContract.RawContacts.CONTENT_URI)
                    .withValue(ContactsContract.RawContacts.ACCOUNT_NAME, null).withValue(ContactsContract.RawContacts.ACCOUNT_TYPE, null).build())
                listOf(ContactsContract.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE to name,
                    ContactsContract.CommonDataKinds.Phone.CONTENT_ITEM_TYPE to phone, ContactsContract.CommonDataKinds.Email.CONTENT_ITEM_TYPE to email).forEach { (type, value) ->
                    ops += ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                        .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, 0)
                        .withValue(ContactsContract.Data.MIMETYPE, type).withValue(ContactsContract.Data.DATA1, value).build()
                }
                ContentUris.parseId(requireNotNull(resolver.applyBatch(ContactsContract.AUTHORITY, ops).first().uri))
            }
            fun permission() = base.checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED
            fun button(id: Int) = compose.onNodeWithText(base.getString(id))
            fun newChat() {
                compose.waitUntil(15_000) { f.model.chat?.ready == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("new-chat-search").assertIsDisplayed()
            }
            fun systemPrompt(allow: Boolean) {
                val target = if (allow) "permission_allow_button" else "permission_deny_button"
                val actual = f.device.wait(Until.findObject(By.res(java.util.regex.Pattern.compile(".*:id/$target"))), 12_000)
                assertNotNull("Android runtime permission prompt must be present", actual)
                f.device.waitForIdle(1_000)
                if (!allow) f.device.takeScreenshot(java.io.File(f.output, "02b-android-contacts-permission.png"))
                actual.click()
                val prompt = By.res(java.util.regex.Pattern.compile(".*:id/permission_message"))
                assertTrue("Wait for Android to finish handling the permission decision", f.device.wait(Until.gone(prompt), 10_000))
                compose.waitUntil(8_000) { f.device.currentPackageName == BuildConfig.APPLICATION_ID }
            }
            try {
                assertFalse("Start with a clean denied permission on the isolated QA package", permission())
                base.getSharedPreferences("phone-contact-permission", 0).edit().clear().commit()
                f.launch(); newChat()
                compose.onNodeWithTag("saved-friend-${service.peer}").assertIsDisplayed()
                f.capture("01-saved-friends")
                compose.onNodeWithTag("new-chat-search").performTextInput("@MAYA")
                compose.onNodeWithTag("saved-friend-${service.peer}").assertExists()
                compose.onNodeWithTag("new-chat-search").performTextReplacement("torres")
                compose.onNodeWithTag("saved-friend-${service.peer}").performClick()
                compose.waitUntil { f.model.selectedPeer == service.peer && f.model.screen == Screen.CONVERSATION }
                f.relaunch { VipiModel(it, NoJourneyModelTranslation, service) }
                newChat()
                compose.onNodeWithTag("saved-friend-${service.peer}").performClick()
                compose.waitUntil { f.model.selectedPeer == service.peer && f.model.screen == Screen.CONVERSATION }
                assertEquals(1, f.model.chat?.threads?.count { it.peer == service.peer })
                assertTrue(service.lookups.isEmpty())
                f.device.pressBack(); newChat()
                val search = compose.onNodeWithTag("new-chat-search")
                search.performTextReplacement("Blocked Person")
                button(R.string.new_chat_no_matches).assertExists()
                search.performTextReplacement("Self Person")
                button(R.string.new_chat_no_matches).assertExists()
                search.performTextClearance()
                button(R.string.new_chat_phone_contacts).performClick()
                button(R.string.phone_contacts_title).assertIsDisplayed()
                assertFalse(permission())
                f.capture("02-contacts-explanation")
                button(R.string.notification_reply_later).performClick()
                assertEquals(BuildConfig.APPLICATION_ID, f.device.currentPackageName); assertFalse(permission())
                button(R.string.new_chat_phone_contacts).performClick()
                button(R.string.continue_action).performClick(); systemPrompt(false)
                button(R.string.phone_contacts_denied).assertIsDisplayed()
                assertFalse(permission())
                button(R.string.notification_reply_later).performClick()
                button(R.string.nav_invite).performClick()
                compose.waitUntil(8_000) { f.device.currentPackageName in setOf("android", "com.android.intentresolver") }
                f.device.pressBack()
                compose.waitUntil(8_000) { f.device.currentPackageName == BuildConfig.APPLICATION_ID }
                button(R.string.new_chat_phone_contacts).performClick()
                button(R.string.phone_contacts_denied).assertIsDisplayed()
                button(R.string.continue_action).performClick(); systemPrompt(true)
                compose.waitUntil(10_000) { permission() && compose.onAllNodesWithText(name).fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithTag("phone-invite-search").performTextInput("Sam Test")
                compose.onNodeWithText(name).performClick()
                val sms = compose.onNodeWithText(base.getString(R.string.phone_text_to, phone))
                val mail = compose.onNodeWithText(base.getString(R.string.phone_email_to, email))
                sms.assertIsDisplayed(); mail.assertIsDisplayed()
                f.capture("03-choose-address")
                sms.performClick()
                compose.waitUntil(12_000) { f.device.currentPackageName != null && f.device.currentPackageName != BuildConfig.APPLICATION_ID }
                val body = f.device.wait(Until.findObject(By.textContains("https://api.mambovipi.app/invite/")), 12_000)
                assertNotNull("System SMS composer must contain the Vipi invitation draft", body)
                f.device.dumpWindowHierarchy(java.io.File(f.output, "04-sms-draft.xml"))
                f.device.takeScreenshot(java.io.File(f.output, "04-sms-draft.png"))
                assertTrue("Synthetic recipient in external SMS UI",
                    java.io.File(f.output, "04-sms-draft.xml").readText().let { it.contains(name) || it.replace(Regex("[ ()-]"), "").contains("2025550127") })
                // The SMS app owns its draft and may keep it when going back.
                // Discard this synthetic draft there, then leave its composer.
                val editor = requireNotNull(f.device.findObject(By.clazz("android.widget.EditText")))
                editor.clear()
                assertFalse(editor.text.orEmpty().contains("/invite/"))
                f.device.pressBack()
                android.os.SystemClock.sleep(450)
                if (f.device.currentPackageName != BuildConfig.APPLICATION_ID) f.device.pressBack()
                android.os.SystemClock.sleep(450)
                if (f.device.currentPackageName != BuildConfig.APPLICATION_ID) {
                    // Some SMS apps leave the user in their own task. Resume
                    // Vipi through the same normal launcher intent as its icon.
                    base.startActivity(requireNotNull(base.packageManager.getLaunchIntentForPackage(BuildConfig.APPLICATION_ID)))
                }
                compose.waitUntil(12_000) { f.device.currentPackageName == BuildConfig.APPLICATION_ID }
                assertTrue(service.lookups.isEmpty())
                val draft = addressedInvitation(InviteAddress(true, email), friendInviteText(base, "alex"))
                assertEquals(Intent.ACTION_SENDTO, draft.action); assertEquals("mailto", draft.data?.scheme)
                assertTrue(draft.data.toString().contains(email)); assertTrue(draft.getStringExtra(Intent.EXTRA_TEXT)!!.contains("/invite/alex"))
            } finally {
                f.stopActivity(); service.close()
                contactsSetup { resolver.delete(ContentUris.withAppendedId(ContactsContract.RawContacts.CONTENT_URI, id), null, null) }
            }
        }
    }
}
