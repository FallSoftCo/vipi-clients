package co.fallsoft.vipi

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.UUID

/** Real activity and account vault, with an isolated group roster and no external transport. */
class AdaptiveInboxJourneyTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun groupOnlyAccountOpensItsConversationAndReturnsToChats() {
        val service = JourneyServices(false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        val group = GroupSnapshot(UUID.randomUUID(), "Saturday language club", 1, "active", listOf(
            GroupMember(service.account, "Alex", "alex", GroupRole.OWNER, 1, null),
            GroupMember(service.peer, "Maya", "maya", GroupRole.MEMBER, 1, null)), emptyList())
        val latest = GroupMessage(UUID.randomUUID(), group.id, 1, 1, service.peer, "Coffee at the station?", 2_000,
            GroupDelivery.RECEIVED)
        service.groupProtocolVersion = 1
        service.groupsRequest = { method, path, _, _ ->
            check(method == "GET" && path == "/v1/groups")
            JSONObject().put("groups", JSONArray().put(group.json())).put("invitations", JSONArray())
        }
        MainActivityJourneyFixture("adaptive-inbox", { app ->
            MessageVault(app, service.account).use { vault ->
                val groups = GroupsStore(vault)
                groups.save(group)
                groups.saveActiveIDs(setOf(group.id))
                groups.saveMessage(latest)
                assertEquals(latest to 1, groups.inboxSummary(group.id))
                groups.saveMessage(latest.copy(id = UUID.randomUUID(), createdAt = 3_000, text = "Private held text",
                    delivery = GroupDelivery.WITHHELD))
                assertEquals(latest to 1, groups.inboxSummary(group.id))
                groups.saveMessage(latest)
                assertEquals(latest to 1, groups.inboxSummary(group.id))
            }
            service.model(app).apply { changeConversationAnimation(false) }
        }).use { fixture ->
            fun capture(name: String) {
                compose.waitForIdle()
                // Capture the actual native window. The fixture also records the full system screen and focused window.
                val roots = compose.onAllNodes(isRoot()).fetchSemanticsNodes()
                if (roots.size == 1) {
                    val image = compose.onRoot().captureToImage().asAndroidBitmap()
                    File(fixture.output, "$name-window.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
                }
                fixture.capture(name)
            }
            fixture.launch()
            compose.waitUntil(30_000) { fixture.model.screen == Screen.HOME && fixture.model.chat?.ready == true }
            val row = compose.onNodeWithTag("inbox-group-row-${group.id}")
            capture("01-inbox")
            row.assertIsDisplayed()
            compose.onNodeWithTag("inbox-empty").assertDoesNotExist()
            compose.onNodeWithText("Private held text").assertDoesNotExist()
            row.performClick()
            compose.waitUntil(10_000) { fixture.model.screen == Screen.GROUPS && fixture.model.inboxGroup == group.id }
            compose.onNodeWithText(group.title).assertIsDisplayed()
            capture("02-group")
            fixture.device.pressBack()
            compose.waitUntil(10_000) { fixture.model.screen == Screen.HOME }
            row.assertIsDisplayed()
            compose.onNodeWithTag("inbox-compose").performClick()
            compose.onNodeWithTag("new-chat-search").assertIsDisplayed()
            capture("03-new-chat")
            compose.onNodeWithText(fixture.base.getString(R.string.new_chat_phone_contacts)).performScrollTo().performClick()
            compose.onNodeWithText(fixture.base.getString(R.string.phone_contacts_title)).assertIsDisplayed()
            capture("04-contact-permission")
            compose.onNodeWithText(fixture.base.getString(R.string.notification_reply_later)).performClick()
            compose.onNodeWithTag("new-group-action").performScrollTo().performClick()
            capture("05-create-group")
            for ((screen, name) in listOf(Screen.SETTINGS to "settings", Screen.HELP to "help",
                    Screen.DELETE_ACCOUNT to "delete", Screen.LANGUAGE to "languages", Screen.ACCOUNT to "sign-in",
                    Screen.WELCOME to "welcome")) {
                compose.runOnIdle { fixture.model.navigate(screen) }
                compose.waitUntil(10_000) { fixture.model.screen == screen }
                capture(name)
            }
        }
    }
}
