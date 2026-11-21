package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID

/** Regular app navigation and native encrypted journals; only the external service is synthetic. */
class StreakJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun chatsAndGroupRowsOpenQualifiedHeadersAndExplainMidnight() {
        val spanish = mapOf(
            "Coffee on Saturday?" to "¿Tomamos un café el sábado?", "See you at the café!" to "¡Nos vemos en el café!",
            "I can bring the bread." to "Puedo llevar el pan.", "Which café did you have in mind?" to "¿En qué café estabas pensando?",
            "The one near the station." to "El que está cerca de la estación.", "See you Saturday!" to "¡Hasta el sábado!",
            "I’ll be there." to "Allí estaré.")
        val service = JourneyServices(false, accountDisplayName = "Alex", peerDisplayName = "Maya", translationFactory = {
            object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String) = spanish.getValue(text)
                override fun close() = Unit
            }
        })
        val other = UUID.randomUUID()
        val groupID = UUID.randomUUID()
        val roster = GroupSnapshot(groupID, "Saturday coffee", 1, "active", listOf(
            GroupMember(service.account, "Alex", "alex", GroupRole.OWNER, 1, null),
            GroupMember(service.peer, "Maya", "maya", GroupRole.MEMBER, 1, null),
            GroupMember(other, "Rafa", "rafa", GroupRole.MEMBER, 1, null)), emptyList())
        service.groupProtocolVersion = if (BuildConfig.GROUPS_QUALIFICATION) 1 else null
        service.groupsRequest = { method, path, _, _ ->
            check(method == "GET")
            when (path) {
                "/v1/groups" -> JSONObject().put("groups", JSONArray().put(roster.json())).put("invitations", JSONArray())
                "/v1/groups/$groupID" -> roster.json()
                else -> error("Unexpected request $method $path")
            }
        }
        val today = System.currentTimeMillis() / ConversationStreaks.DAY_MS
        MainActivityJourneyFixture("streaks", { app ->
            MessageVault(app, service.account).use { vault ->
                ConversationHistory(vault)
                vault.transaction {
                    for ((i, person) in listOf(service.peer to "Maya", other to "Rafa").withIndex()) {
                        val (peer, name) = person
                        vault.put("contact", peer.toString(), ChatProfile(peer, "friend_$i", name).json().toString().toByteArray())
                        val days = if (i == 0) 7 else 2
                        for (ago in 0 until days) for (out in listOf(true, false)) {
                            val time = (today - ago) * ConversationStreaks.DAY_MS + 4_000 - 1_000 * i + if (out) 0 else 500
                            val e = ChatEnvelope(UUID.randomUUID(), if (out) service.account else peer, if (out) peer else service.account,
                                time, 1, byteArrayOf(1))
                            val kind = if (out) "outgoing" else "incoming"
                            val text = when {
                                ago % 2 == 1 -> if (out) "Which café did you have in mind?" else "The one near the station."
                                out -> "Coffee on Saturday?"
                                i == 0 -> "See you at the café!"
                                else -> "I can bring the bread."
                            }
                            vault.put(kind, e.id.toString(), StoredChat(e, text, "delivered", seen = true).encode())
                            ConversationHistory.record(vault, kind, e.id, peer, time, unread = !out && ago == 0)
                            if (!out && peer == service.peer) service.generatedPeerReplies[e.id] = text
                        }
                    }
                }
                val groups = GroupsStore(vault)
                groups.save(roster)
                for (ago in 0 until 3) for (author in listOf(service.peer, other)) {
                    groups.saveMessage(GroupMessage(UUID.randomUUID(), groupID, 1, 1, author, if (author == other) "See you Saturday!" else "I’ll be there.",
                        (today - ago) * ConversationStreaks.DAY_MS + if (author == other) 500 else 0, GroupDelivery.RECEIVED))
                }
            }
            service.model(app)
        }).use { f ->
            try {
                fun badge(n: Int) = compose.onNodeWithContentDescription(f.base.getString(R.string.streak_days, java.text.NumberFormat.getIntegerInstance(f.base.resources.configuration.locales[0]).format(n)), useUnmergedTree = true)
                fun awaitBadge(n: Int) = compose.waitUntil(20_000) { runCatching { badge(n).isDisplayed() }.getOrDefault(false) }
                fun capture(name: String) {
                    compose.waitForIdle()
                    val latch = java.util.concurrent.CountDownLatch(1)
                    f.instrumentation.runOnMainSync {
                        val activity = androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance()
                            .getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED).single()
                        val view = activity.window.decorView
                        view.viewTreeObserver.registerFrameCommitCallback { view.postDelayed({ latch.countDown() }, 160) }
                        view.invalidate()
                    }
                    check(latch.await(4, java.util.concurrent.TimeUnit.SECONDS))
                    f.capture(name)
                }
                f.instrumentation.runOnMainSync {
                    f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES)
                    if (androidx.test.platform.app.InstrumentationRegistry.getArguments().getString("dark") == "true")
                        f.model.changeAppearance(Appearance.DARK)
                }
                f.launch(); awaitBadge(7); badge(2).assertIsDisplayed()
                compose.onNodeWithTag("inbox-unread-${service.peer}", true).assertIsDisplayed()
                capture("01-chats-days-and-unread")
                compose.onNodeWithTag("inbox-row-${service.peer}").performClick()
                awaitBadge(7); capture("02-direct-seven-days")
                badge(7).performClick(); compose.onNodeWithText(f.base.getString(R.string.streak_direct_rule)).assertIsDisplayed()
                capture("03-direct-explanation")
                compose.onNodeWithText(f.base.getString(R.string.lookup_close)).performClick()
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back)).performClick()
                compose.waitUntil(12_000) { f.model.screen == Screen.HOME }
                if (BuildConfig.GROUPS_QUALIFICATION) {
                    compose.onNodeWithTag("inbox-compose").performClick()
                    compose.onNodeWithTag("open-groups").performScrollTo().performClick()
                    awaitBadge(3); capture("04-group-list")
                    compose.onNodeWithText(roster.title).performClick()
                    awaitBadge(3); capture("05-group-three-days")
                    badge(3).performClick(); compose.onNodeWithText(f.base.getString(R.string.streak_group_rule)).assertIsDisplayed()
                    capture("06-group-explanation")
                }
                assertEquals(0, service.friendPosts.get())
            } finally { f.stopActivity(); service.close() }
        }
    }
}
