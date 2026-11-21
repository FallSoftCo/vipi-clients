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

    @Test fun openCreateAndInviteFromChats() {
        require(BuildConfig.GROUPS_QUALIFICATION)
        val service = JourneyServices(profileRequired = false, peerDisplayName = "Maya")
        var snapshot: GroupSnapshot? = null
        var inviteCalls = 0
        service.groupsRequest = { method, path, body, device ->
            when {
                method == "GET" && path == "/v1/groups" -> JSONObject()
                    .put("groups", JSONArray(listOfNotNull(snapshot?.json()))).put("invitations", JSONArray())
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
                val friend = ChatProfile(service.peer, "maya", "Maya")
                vault.put("contact", service.peer.toString(), friend.json().toString().toByteArray())
            } }
            service.model(app)
        }).use { fixture ->
            try {
                fixture.launch()
                compose.waitUntil(15_000) { fixture.model.chat?.ready == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("open-groups").performScrollTo().performClick()
                compose.waitUntil(10_000) { fixture.model.chat?.groups?.loaded == true }
                compose.onAllNodesWithText("Create group").onFirst().performClick()
                compose.onNodeWithText("Maximum 16 people").assertIsDisplayed()
                compose.onNodeWithText("Group name").performTextInput("Saturday practice")
                compose.onNodeWithText("Maya").performScrollTo().performClick()
                compose.onNodeWithText("2 of 16 people selected, including you").assertExists()
                fixture.capture("01-group-member-selection")
                compose.onNodeWithText("Create group and invite 1").performScrollTo().performClick()
                compose.waitUntil(15_000) { inviteCalls == 1 && fixture.model.chat?.groups?.busy == false }
                compose.onNodeWithText("Message the group").assertExists()
                compose.onNodeWithTag("conversation-immersion").performClick()
                compose.runOnIdle { assertEquals(ImmersionMode.FULL_MESSAGES, fixture.model.chat?.translations?.mode) }
                compose.onNodeWithTag("conversation-immersion").performClick()
                compose.runOnIdle { assertEquals(ImmersionMode.NEW_WORD, fixture.model.chat?.translations?.mode) }
                compose.onNodeWithTag("conversation-autoplay").assertIsDisplayed()
                fixture.capture("02-group-conversation")
                compose.onNodeWithContentDescription("Group info").performClick()
                compose.onNodeWithText("Saturday practice", substring = true).assertExists()
                fixture.capture("03-group-membership")
                compose.runOnIdle {
                    val saved = requireNotNull(fixture.model.chat?.groups?.group(requireNotNull(snapshot).id))
                    assertEquals(listOf(service.peer), saved.invitations.map { it.user })
                    assertEquals(listOf(service.account), saved.members.map { it.id })
                }
            } finally { fixture.stopActivity(); service.close() }
        }
    }
}
