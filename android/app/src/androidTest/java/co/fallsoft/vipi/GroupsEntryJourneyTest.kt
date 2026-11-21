package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID

class GroupsEntryJourneyTest {
    @get:Rule val compose = createEmptyComposeRule()

    private fun capture(fixture: MainActivityJourneyFixture, name: String) {
        compose.mainClock.advanceTimeBy(400)
        compose.waitForIdle()
        repeat(2) {
            val latch = java.util.concurrent.CountDownLatch(1)
            fixture.instrumentation.runOnMainSync {
                val activity = androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance()
                    .getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED).single()
                val root = activity.window.decorView
                root.viewTreeObserver.registerFrameCommitCallback { latch.countDown() }
                root.invalidate()
            }
            check(latch.await(4, java.util.concurrent.TimeUnit.SECONDS)) { "Native frame did not commit" }
        }
        fixture.capture(name)
    }

    @Test fun draftSurvivesReopenAndCapabilityChangeWithoutSending() {
        val service = JourneyServices(profileRequired = false, peerDisplayName = "Maya")
        MainActivityJourneyFixture("group-draft", { app ->
            MessageVault(app, service.account).use { vault -> vault.transaction {
                val person = ChatProfile(service.peer, "maya", "Maya")
                vault.put("contact", person.id.toString(), person.json().toString().toByteArray())
            } }
            service.model(app)
        }).use { fixture ->
            try {
                fixture.launch()
                compose.waitUntil(15_000) { fixture.model.chat?.ready == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("open-groups").assertDoesNotExist()
                compose.onNodeWithTag("saved-friend-${service.peer}").assertIsDisplayed()
                capture(fixture, "00-regular-contact-picker")
                compose.onNodeWithTag("new-group-action").performClick()
                compose.onNodeWithText("Save draft").assertIsNotEnabled()
                fixture.device.waitForIdle()
                capture(fixture, "00-new-group-draft-form")
                compose.onNodeWithText("Group name").performTextInput("Friday book club")
                fixture.hideKeyboard()
                compose.onNodeWithText("Save draft").performClick()
                compose.onNodeWithText("Draft saved on this phone.").assertIsDisplayed()
                compose.onNodeWithText("Back").performClick()
                compose.onNodeWithTag("new-group-action").performClick()
                compose.onNodeWithText("Friday book club").assertExists()
                compose.onNodeWithTag("new-group-roster").performScrollToNode(hasText("Maya"))
                compose.onNodeWithText("Maya").performClick()
                compose.onNodeWithText("Save draft").performClick()
                fixture.device.waitForIdle()
                compose.onNodeWithText("Draft saved on this phone.").assertIsDisplayed()
                android.os.SystemClock.sleep(600)
                capture(fixture, "01-saved-draft")
                compose.runOnIdle {
                    val local = requireNotNull(fixture.model.chat?.groups)
                    assertEquals(GroupCreationDraft("Friday book club", setOf(service.peer)), local.store.creationDraft())
                    assertTrue(local.groups.isEmpty())
                    MessageVault(fixture.isolated, service.account).use { reopened ->
                        assertEquals(GroupCreationDraft("Friday book club", setOf(service.peer)), GroupsStore(reopened).creationDraft())
                    }
                    MessageVault(fixture.isolated, UUID.randomUUID()).use { other -> assertNull(GroupsStore(other).creationDraft()) }
                }
                compose.onNodeWithTag("new-group-roster").performScrollToNode(hasText("Group name"))
                compose.onNodeWithText("Group name").performTextReplacement("")
                fixture.hideKeyboard()
                compose.onNodeWithText("Save draft").assertIsEnabled().performClick()
                compose.runOnIdle { assertEquals(GroupCreationDraft("", setOf(service.peer)), fixture.model.chat?.groups?.store?.creationDraft()) }
                compose.onNodeWithText("Group name").performTextInput("Friday book club")
                fixture.hideKeyboard()
                compose.onNodeWithText("Save draft").performClick()
                compose.onNodeWithText("Back").performClick()
                fixture.device.pressBack()
                service.groupProtocolVersion = 1
                fixture.recreate()
                compose.waitUntil(12_000) { fixture.model.chat?.groups?.remoteAvailable == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("new-group-action").performClick()
                compose.onNodeWithText("Friday book club").assertExists()
                compose.onNodeWithText("Create group and invite 1").assertIsEnabled()
                compose.runOnIdle { assertTrue(requireNotNull(fixture.model.chat?.groups).groups.isEmpty()) }
            } finally { fixture.stopActivity(); service.close() }
        }
    }

    @Test fun openCreateAndInviteFromChats() {
        require(BuildConfig.GROUPS_QUALIFICATION)
        val service = JourneyServices(profileRequired = false, peerDisplayName = "Maya")
        var snapshot: GroupSnapshot? = null
        var inviteCalls = 0
        val invitation = UUID.randomUUID()
        val invitedGroup = UUID.randomUUID()
        var declined = false
        service.groupProtocolVersion = 1
        service.groupsRequest = { method, path, body, device ->
            when {
                method == "GET" && path == "/v1/groups" -> JSONObject()
                    .put("groups", JSONArray(listOfNotNull(snapshot?.json()))).put("invitations", JSONArray().apply {
                        if (!declined) put(JSONObject().put("id", invitation).put("group_id", invitedGroup)
                            .put("title", "Book club").put("invited_by", service.peer)
                            .put("expires_at", "2030-01-01T00:00:00Z").put("epoch", 1))
                    })
                method == "POST" && path == "/v1/groups/$invitedGroup/invitations/$invitation/decline" -> {
                    check(!declined)
                    declined = true
                    JSONObject()
                }
                method == "POST" && path == "/v1/groups" -> {
                    check(snapshot == null)
                    val fields = requireNotNull(body)
                    GroupSnapshot(fields.uuid("id"), fields.getString("title"), 1, "active",
                        listOf(GroupMember(service.account, "Alex", "alex", GroupRole.OWNER, 1, device.id)), emptyList())
                        .also { snapshot = it }.json()
                }
                method == "POST" && path == "/v1/groups/${snapshot?.id}/invitations" -> {
                    val group = requireNotNull(snapshot)
                    val fields = requireNotNull(body)
                    check(fields.uuid("user_id") == service.peer && fields.getInt("expected_epoch") == group.epoch)
                    inviteCalls++
                    group.copy(epoch = 2, invitations = listOf(GroupPendingInvitation(fields.uuid("request_id"), service.peer,
                        service.account, "2030-01-01T00:00:00Z", "pending"))).also { snapshot = it }.json()
                }
                else -> error("Unexpected group fixture request $method $path")
            }
        }
        MainActivityJourneyFixture("groups-entry", { app ->
            app.getSharedPreferences("preferences", 0).edit().putBoolean("animateConversationBackground", false).commit()
            MessageVault(app, service.account).use { vault -> vault.transaction {
                repeat(125) { index ->
                    val person = ChatProfile(UUID.nameUUIDFromBytes("group-picker-$index".toByteArray()), "zfriend$index", "Z Friend $index")
                    vault.put("contact", person.id.toString(), person.json().toString().toByteArray())
                }
                val friend = ChatProfile(service.peer, "maya", "Maya")
                vault.put("contact", service.peer.toString(), friend.json().toString().toByteArray())
            } }
            service.model(app)
        }).use { fixture ->
            try {
                fixture.launch()
                compose.waitUntil(15_000) { fixture.model.chat?.ready == true }
                compose.onNodeWithTag("new-group-action").assertDoesNotExist()
                compose.onAllNodesWithTag("inbox-compose").assertCountEquals(1)
                val newAction = compose.onNodeWithText(fixture.base.getString(R.string.compose_new_action))
                fixture.device.waitForIdle()
                android.os.SystemClock.sleep(350)
                capture(fixture, "00-chats-new")
                compose.onNodeWithTag("inbox-compose").assertIsDisplayed()
                newAction.assertIsDisplayed()
                compose.onNodeWithContentDescription(fixture.base.getString(R.string.nav_settings)).performClick()
                compose.onNodeWithText(fixture.base.getString(R.string.privacy_claim_chat_sale)).performScrollTo().assertIsDisplayed()
                fixture.device.waitForIdle()
                capture(fixture, "sticker-settings")
                fixture.device.pressBack()
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("saved-friend-${service.peer}").assertIsDisplayed()
                compose.onNodeWithTag("new-group-action").assertIsDisplayed()
                capture(fixture, "00-new-chat-friends-contacts-groups")
                compose.onNodeWithTag("new-chat-search").performTextInput("Ma")
                fixture.hideKeyboard()
                compose.onNodeWithTag("new-group-action").assertIsDisplayed().performClick()
                compose.onNodeWithText("Group name").assertIsDisplayed()
                compose.onNodeWithText("Back").assertIsDisplayed().performClick()
                compose.waitUntil(10_000) { fixture.model.screen == Screen.NEW_CHAT }
                compose.onNodeWithTag("new-chat-search").assertTextContains("Ma")
                compose.onNodeWithTag("open-groups").performClick()
                compose.waitUntil(10_000) { fixture.model.chat?.groups?.invitations?.any { it.id == invitation } == true }
                compose.onNodeWithText("Book club").assertIsDisplayed()
                fixture.device.waitForIdle()
                android.os.SystemClock.sleep(350)
                capture(fixture, "00a-retained-group-invitation")
                compose.onNodeWithText("Join group").assertIsEnabled()
                compose.onNodeWithText("Decline").performClick()
                compose.waitUntil(10_000) { declined && fixture.model.chat?.groups?.invitations?.isEmpty() == true }
                compose.onNodeWithText("Back").performClick()
                compose.waitUntil(10_000) { fixture.model.screen == Screen.NEW_CHAT }
                compose.onNodeWithTag("new-chat-search").assertTextContains("Ma")
                fixture.device.pressBack()
                compose.waitUntil(10_000) { fixture.model.screen == Screen.HOME }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithText("Z Friend 0").assertExists()
                compose.onNodeWithTag("saved-friend-${service.peer}").performClick()
                compose.waitUntil(10_000) { fixture.model.selectedPeer == service.peer && fixture.model.screen == Screen.CONVERSATION }
                assertTrue(service.lookups.isEmpty())
                fixture.device.pressBack()
                compose.waitUntil(10_000) { fixture.model.screen == Screen.HOME }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("new-group-action").assertIsDisplayed()
                compose.onNodeWithTag("saved-friend-${service.peer}").assertIsDisplayed()
                fixture.device.waitForIdle()
                compose.onNodeWithText(fixture.base.getString(R.string.new_chat_phone_contacts)).performClick()
                compose.onNodeWithText(fixture.base.getString(R.string.phone_contacts_title)).assertIsDisplayed()
                fixture.device.waitForIdle()
                capture(fixture, "sticker-contacts")
                compose.onNodeWithText(fixture.base.getString(R.string.notification_reply_later)).performClick()
                compose.onNodeWithTag("new-group-action").performScrollTo().performClick()
                compose.onNodeWithText("Group name").assertIsDisplayed()
                fixture.device.pressBack()
                compose.waitUntil(10_000) { fixture.model.screen == Screen.NEW_CHAT }
                compose.onNodeWithTag("new-group-action").performScrollTo().performClick()
                compose.onNodeWithText("Maximum 16 people").assertIsDisplayed()
                compose.onNodeWithText("Create group").assertIsNotEnabled()
                val config = fixture.base.resources.configuration
                val spot = compose.onNodeWithTag("screen-spot", useUnmergedTree = true)
                if (config.fontScale < 1.5f && config.screenWidthDp >= 360 && config.screenHeightDp >= 480)
                    spot.assertIsDisplayed().assertHasNoClickAction()
                else spot.assertDoesNotExist()
                fixture.device.waitForIdle()
                capture(fixture, "00b-new-group-illustration")
                compose.onNodeWithText("Group name").performTextInput("Saturday practice")
                spot.assertDoesNotExist()
                compose.onNodeWithText("Create group").assertIsDisplayed().assertIsNotEnabled()
                compose.onNodeWithTag("new-group-roster").performScrollToNode(hasText("Maya"))
                compose.onNodeWithText("Maya").performClick()
                compose.onNodeWithText("Create group and invite 1").assertIsDisplayed().assertIsEnabled()
                fixture.hideKeyboard()
                compose.waitForIdle()
                android.os.SystemClock.sleep(500)
                capture(fixture, "01-group-member-selection")
                compose.onNodeWithText("Create group and invite 1").assertIsDisplayed().assertIsEnabled().performClick()
                compose.waitUntil(15_000) { inviteCalls == 1 && fixture.model.chat?.groups?.busy == false }
                compose.onNodeWithText("Message the group").assertExists()
                compose.onNodeWithTag("conversation-immersion").performClick()
                compose.runOnIdle { assertEquals(ImmersionMode.FULL_MESSAGES, fixture.model.chat?.translations?.mode) }
                compose.onNodeWithTag("conversation-immersion").performClick()
                compose.runOnIdle { assertEquals(ImmersionMode.NEW_WORD, fixture.model.chat?.translations?.mode) }
                compose.onNodeWithTag("conversation-autoplay").assertIsDisplayed()
                capture(fixture, "02-group-conversation")
                compose.onNodeWithContentDescription("Group info").performClick()
                compose.onNodeWithText("Saturday practice", substring = true).assertExists()
                capture(fixture, "03-group-membership")
                compose.runOnIdle {
                    val saved = requireNotNull(fixture.model.chat?.groups?.group(requireNotNull(snapshot).id))
                    assertEquals(listOf(service.peer), saved.invitations.map { it.user })
                    assertEquals(listOf(service.account), saved.members.map { it.id })
                }
            } finally { fixture.stopActivity(); service.close() }
        }
    }
}
