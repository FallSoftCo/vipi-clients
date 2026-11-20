package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import kotlinx.coroutines.CompletableDeferred
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Actual production root/navigation + encrypted local history. Explicit synthetic
 * history and a held translation boundary; no live users, SDK/voice certification,
 * network delivery or fabricated translation outputs. */
class InboxJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private data class Row(val peer: UUID, val name: String, val text: String, val time: Long,
        val outgoing: Boolean = false, val unread: Int = 0, val id: UUID = UUID.randomUUID())
    private fun screen(f: MainActivityJourneyFixture, value: Screen) = compose.waitUntil(15_000) { f.model.screen == value && f.model.chat?.ready == true }
    private fun paint(f: MainActivityJourneyFixture, name: String) {
        compose.mainClock.advanceTimeBy(300); compose.waitForIdle()
        repeat(2) {
            val latch = CountDownLatch(1)
            f.instrumentation.runOnMainSync {
                val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single() as Activity
                val root = activity.window.decorView; check(root.isHardwareAccelerated)
                root.viewTreeObserver.registerFrameCommitCallback { latch.countDown() }; root.invalidate()
            }
            check(latch.await(3, TimeUnit.SECONDS)) { "Native frame did not commit" }
        }
        f.capture(name)
    }
    private fun geometry(f: MainActivityJourneyFixture, name: String, rows: List<Row>) {
        val window = f.unobscuredWindow()
        val list = compose.onNodeWithTag("inbox-list").fetchSemanticsNode().boundsInWindow
        val bounds = JSONArray()
        for (row in rows) {
            val b = compose.onNodeWithTag("inbox-row-${row.peer}").fetchSemanticsNode().boundsInWindow
            assertTrue("Whole row width stays within screen", b.left >= window.left && b.right <= window.right)
            assertTrue("Native row has >=48dp touch height", b.height >= 48 * f.base.resources.displayMetrics.density)
            val date = compose.onNodeWithTag("inbox-date-${row.peer}", useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
            assertTrue("Date fits within its row", date.left >= b.left && date.right <= b.right && date.top >= b.top && date.bottom <= b.bottom)
            bounds.put(JSONObject().put("peer",row.peer).put("name",row.name).put("row",b.toString()).put("date",date.toString()))
        }
        File(f.output,"$name-bounds.json").writeText(JSONObject().put("list",list.toString()).put("rows",bounds).toString(2))
    }
    @Test fun settingsSelectsPrivateLocalPreviewsAndHonorsRedaction() {
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        val incoming = Row(service.peer, "Maya", "Coffee at six?", System.currentTimeMillis(), unread = 1)
        MainActivityJourneyFixture("settings-previews", { app -> seed(app, service, listOf(incoming)); service.model(app) }).use { f ->
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick()
                screen(f, Screen.SETTINGS)
                compose.onAllNodesWithText(f.base.getString(R.string.settings_title)).assertCountEquals(1)
                paint(f, "settings-profile-and-chats")
                val toggle = compose.onNodeWithTag("settings-message-previews")
                toggle.performScrollTo().assertIsOff()
                val generic = f.base.getString(R.string.ui_3abeae7a3bed)
                fun notification(unlocked: Boolean) = requireNotNull(PushDelivery.buildNotification(f.base, f.model.chat!!, unlocked))
                fun body(note: android.app.Notification) = note.extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString()
                compose.runOnIdle { assertEquals(generic, body(notification(true))) }
                compose.onNodeWithText(generic).performScrollTo(); paint(f, "settings-preview-private")
                toggle.performScrollTo().performClick().assertIsOn()
                compose.onNodeWithText(f.base.getString(R.string.settings_sample_message)).performScrollTo(); paint(f, "settings-preview-content")
                compose.runOnIdle {
                    val privateNote = notification(true)
                    assertEquals(incoming.text, body(privateNote)); assertEquals("Maya", privateNote.extras.getString(android.app.Notification.EXTRA_TITLE))
                    assertEquals(android.app.Notification.VISIBILITY_PRIVATE, privateNote.visibility)
                    assertEquals(generic, body(privateNote.publicVersion)); assertEquals(generic, body(notification(false)))
                }
                f.relaunch(service::model); screen(f, Screen.HOME)
                compose.runOnIdle {
                    assertTrue(f.model.chat!!.notificationPreviews)
                    assertEquals(incoming.text, body(notification(true)))
                    f.model.chat!!.markRead(service.peer)
                    assertNull(PushDelivery.buildNotification(f.base, f.model.chat!!, true))
                }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick(); screen(f, Screen.SETTINGS)
                toggle.performScrollTo().performClick().assertIsOff()
                compose.onNodeWithText(f.base.getString(R.string.settings_theme)).performScrollTo().performClick()
                compose.onNodeWithText(f.base.getString(R.string.appearance_dark)).performClick()
                compose.onNodeWithText(f.base.getString(R.string.nav_help)).performScrollTo()
                paint(f, "settings-dark-about")
                service.assertNoPurchase()
            } finally { f.stopActivity(); service.close() }
        }
    }

    @Test fun waterInboxEmptyHasTextureAndKeepsOneNewChatAction() = emptyInbox(waterReview = true)
    @Test fun waterInboxRowsStayFixedOverMovingWaterAndNavigate() = populated(captureOnly = false, waterReview = true)
    @Test fun emptyInboxHasOnePrimaryActionAndNativeLookupNavigation() = emptyInbox(waterReview = false)
    private fun emptyInbox(waterReview: Boolean) {
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        MainActivityJourneyFixture("inbox-empty", service::model).use { f ->
            try {
                f.launch(); screen(f,Screen.HOME)
                compose.onNodeWithTag("inbox-empty").assertIsDisplayed()
                compose.onAllNodesWithTag("inbox-compose").assertCountEquals(1)
                compose.onNodeWithTag("inbox-compose").assertIsEnabled().assertIsDisplayed()
                if (waterReview) {
                    for (appearance in listOf(Appearance.LIGHT, Appearance.DARK)) {
                        compose.runOnIdle { f.model.changeAppearance(appearance); f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES) }
                        paint(f, "water-empty-${appearance.name.lowercase()}")
                    }
                    compose.onNodeWithTag("inbox-compose").performClick(); screen(f, Screen.NEW_CHAT)
                    compose.onNode(hasSetTextAction()).assertIsDisplayed(); paint(f,"water-new-chat-before-system-back")
                    f.device.pressBack(); screen(f, Screen.HOME)
                    compose.onAllNodesWithTag("inbox-compose").assertCountEquals(1)
                    service.assertNoPurchase(); return
                }
                paint(f,"01-empty")
                compose.onNodeWithTag("inbox-compose").performClick(); screen(f,Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.nav_invite)).performScrollTo().assertIsDisplayed()
                paint(f,"02-new-chat")
                compose.onNodeWithText(f.base.getString(R.string.nav_invite)).performClick()
                compose.waitUntil(8_000) { f.device.currentPackageName in setOf("android", "com.android.intentresolver") }
                f.device.waitForIdle(); f.capture("03-native-share")
                f.device.pressBack()
                compose.waitUntil(8_000) { f.device.currentPackageName == BuildConfig.APPLICATION_ID }
                compose.onNode(hasSetTextAction()).assertIsDisplayed()
                paint(f,"04-share-cancelled")
                compose.onNode(hasSetTextAction()).performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction()
                screen(f,Screen.CONVERSATION); assertEquals(service.peer,f.model.selectedPeer)
                paint(f,"05-found-friend")
                f.device.pressBack(); screen(f,Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick(); screen(f,Screen.SETTINGS)
                compose.onNodeWithText(f.base.getString(R.string.settings_title)).assertIsDisplayed()
                paint(f,"06-settings-before-system-back")
                f.device.pressBack(); screen(f,Screen.HOME)
                compose.onNodeWithTag("inbox-empty").assertIsDisplayed(); service.assertNoPurchase()
            } catch (error: Throwable) { runCatching { paint(f,"failure") }.onFailure { runCatching { f.capture("failure-uncommitted") } }; throw error }
            finally { f.stopActivity(); service.close() }
        }
    }
    @Test fun populatedInboxKeepsOriginalPendingPreviewsUnreadDatesAndRowNavigation() = populated(captureOnly = false)
    @Test fun decorativeAvatarsFitWithLargestText() = populated(captureOnly = true)
    private fun populated(captureOnly: Boolean, waterReview: Boolean = false) {
        val held = CompletableDeferred<Unit>()
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya", translationFactory = {
            object : LanguageTranslation {
                override suspend fun prepare(source: String,target: String,cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String,target: String) = true
                override suspend fun translate(text: String,source: String,target: String): String { held.await(); error("Screenshot translation gate must stay held") }
                override fun close() = Unit
            }
        })
        val now = System.currentTimeMillis()
        val rows = listOf(
            Row(service.peer,"Maya","Coffee at six? I found a quiet place ☕",now-60_000,unread=3),
            Row(UUID.randomUUID(),"Alexandria Fernández-Sørensen","The photos are ready — take a look when you can.",now-3_600_000),
            Row(UUID.randomUUID(),"Sam","I will bring the book. See you there!",now-86_400_000,outgoing=true),
            Row(UUID.randomUUID(),"ليلى منصور","هل نلتقي غدًا؟ 🌿",now-3*86_400_000L,unread=1),
            Row(UUID.randomUUID(),"Renée","The weekend walk was lovely.",now-12*86_400_000L),
            Row(UUID.randomUUID(),"Kenji","Thanks! That works for me.",now-400*86_400_000L,outgoing=true))
        MainActivityJourneyFixture("inbox-populated", { app -> seed(app,service,rows); service.model(app) }).use { f ->
            try {
                f.instrumentation.runOnMainSync { f.model.selectTarget("zh"); f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES); f.model.changeAppearance(Appearance.LIGHT) }
                f.launch(); screen(f,Screen.HOME)
                compose.onNodeWithTag("inbox-empty").assertDoesNotExist()
                compose.onNodeWithTag("inbox-compose").assertIsEnabled()
                // Check every real row by scrolling it into the actual viewport;
                // compact landscape must not assume six rows fit at once.
                rows.forEachIndexed { index, row ->
                    compose.onNodeWithTag("inbox-list").performScrollToIndex(index)
                    compose.onNodeWithTag("inbox-row-${row.peer}").assertIsDisplayed()
                    compose.onNodeWithTag("home-message-preview-${row.id}", useUnmergedTree=true).assertTextEquals(row.text)
                    if(row.unread>0) compose.onNodeWithTag("inbox-unread-${row.peer}",useUnmergedTree=true).assertIsDisplayed()
                }
                compose.onNodeWithTag("inbox-list").performScrollToIndex(0)
                if (waterReview) {
                    val originalBounds = compose.onNodeWithTag("inbox-row-${service.peer}").fetchSemanticsNode().boundsInWindow
                    for (appearance in listOf(Appearance.LIGHT, Appearance.DARK)) {
                        compose.runOnIdle { f.model.changeAppearance(appearance) }
                        paint(f, "water-populated-${appearance.name.lowercase()}-deep")
                        compose.runOnIdle { f.model.selectImmersionMode(ImmersionMode.NEW_WORD) }
                        paint(f, "water-populated-${appearance.name.lowercase()}-shallow")
                        assertEquals("Decoration must never change native row geometry", originalBounds,
                            compose.onNodeWithTag("inbox-row-${service.peer}").fetchSemanticsNode().boundsInWindow)
                        compose.runOnIdle { f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES) }
                    }
                    compose.runOnIdle { f.model.changeConversationAnimation(false) }
                    paint(f, "water-paused-before"); Thread.sleep(900); paint(f, "water-paused-after")
                    compose.onNodeWithTag("inbox-row-${service.peer}").performClick(); screen(f, Screen.CONVERSATION)
                    assertEquals(service.peer, f.model.selectedPeer)
                    compose.onNodeWithTag("message-input").assertIsDisplayed(); paint(f,"water-friend-before-system-back")
                    f.device.pressBack(); screen(f, Screen.HOME)
                    compose.onNodeWithTag("inbox-list").performScrollToIndex(rows.lastIndex)
                    compose.onNodeWithTag("inbox-row-${rows.last().peer}").assertIsDisplayed()
                    compose.onNodeWithTag("inbox-compose").performClick(); screen(f, Screen.NEW_CHAT)
                    compose.onNode(hasSetTextAction()).assertIsDisplayed(); paint(f,"water-new-chat-before-system-back")
                    f.device.pressBack(); screen(f, Screen.HOME)
                    service.assertNoPurchase(); return
                }
                geometry(f,"01-populated-day",rows.take(1)); paint(f,"01-populated-day")
                compose.runOnIdle { f.model.changeAppearance(Appearance.DARK) }; paint(f,"02-populated-night")
                compose.onAllNodesWithTag("inbox-compose").assertCountEquals(1)
                val fabNode=compose.onNodeWithTag("inbox-compose").assertIsEnabled().assertIsDisplayed().fetchSemanticsNode()
                assertEquals(androidx.compose.ui.semantics.Role.Button,fabNode.config[SemanticsProperties.Role])
                val fab=fabNode.boundsInWindow;val window=f.unobscuredWindow();val density=f.base.resources.displayMetrics.density
                val rtl=f.base.resources.configuration.layoutDirection==android.view.View.LAYOUT_DIRECTION_RTL
                assertTrue("FAB has a real >=48dp target",fab.width>=48*density&&fab.height>=48*density)
                assertTrue("FAB stays inside safe gesture/window bounds",fab.left>=window.left&&fab.right<=window.right&&fab.top>=window.top&&fab.bottom<=window.bottom)
                val paneWidth=minOf(window.width().toFloat(),680*density)
                val paneLeft=window.exactCenterX()-paneWidth/2;val paneRight=paneLeft+paneWidth
                if(rtl)assertTrue("RTL FAB is near the pane trailing left edge",fab.left>=paneLeft&&fab.left<=paneLeft+24*density)
                else assertTrue("LTR FAB is near the pane trailing right edge",fab.right<=paneRight&&fab.right>=paneRight-24*density)
                compose.onNodeWithTag("inbox-list").performScrollToIndex(rows.lastIndex)
                val finalRow=compose.onNodeWithTag("inbox-row-${rows.last().peer}").assertIsDisplayed().fetchSemanticsNode().boundsInWindow
                assertTrue("Final complete row scrolls above FAB with breathing room",finalRow.bottom<=fab.top-8*density)
                File(f.output,"fab-geometry.json").writeText(JSONObject().put("fab",fab.toString()).put("last_row",finalRow.toString()).put("safe_window",window.toString()).put("rtl",rtl).put("font_scale",f.base.resources.configuration.fontScale).put("width_px",f.device.displayWidth).toString(2))
                paint(f,"03-last-row-clear-fab")
                compose.onNodeWithTag("inbox-compose").performClick();screen(f,Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().assertIsDisplayed();paint(f,"04-fab-new-chat")
                f.device.pressBack();screen(f,Screen.HOME)
                compose.onNodeWithTag("inbox-row-${rows.last().peer}").assertIsDisplayed();paint(f,"05-fab-back-keeps-history-position")
                if (captureOnly) {
                    check(f.base.resources.configuration.fontScale >= 1.5f)
                    service.assertNoPurchase(); return
                }
                // Older dated rows remain reachable; long names never displace dates offscreen.
                compose.onNodeWithTag("inbox-list").performScrollToIndex(rows.lastIndex)
                compose.onNodeWithTag("inbox-row-${rows.last().peer}").assertIsDisplayed(); paint(f,"03-older-date")
                compose.onNodeWithTag("inbox-list").performScrollToIndex(0)
                compose.onNodeWithTag("inbox-row-${service.peer}").performClick(); screen(f,Screen.CONVERSATION)
                assertEquals(service.peer,f.model.selectedPeer)
                compose.onNodeWithTag("message-input").performTextInput("Keep this draft ☕")
                f.device.pressBack() // dismiss native IME first
                compose.waitForIdle()
                if (f.model.screen == Screen.CONVERSATION) f.device.pressBack()
                screen(f,Screen.HOME)
                assertEquals("Keep this draft ☕",f.model.chat!!.compose(service.peer))
                compose.onNodeWithTag("inbox-unread-${service.peer}",useUnmergedTree=true).assertDoesNotExist()
                paint(f,"04-after-opening-unread")
                service.assertNoPurchase(); assertFalse(held.isCompleted)
            } catch (error: Throwable) { runCatching { paint(f,"failure") }.onFailure { runCatching { f.capture("failure-uncommitted") } }; throw error }
            finally { f.stopActivity(); held.cancel(); service.close() }
        }
    }
    private fun seed(app: Application,service: JourneyServices,rows: List<Row>) {
        MessageVault(app,service.account).use { vault ->
            ConversationHistory(vault)
            vault.transaction {
                for ((index,row) in rows.withIndex()) {
                    vault.put("contact",row.peer.toString(),ChatProfile(row.peer,"friend_$index",row.name).json().toString().toByteArray())
                    repeat(maxOf(1,row.unread)) { n ->
                        val id=if(n==0) row.id else UUID.randomUUID(); val time=row.time-n
                        val envelope=ChatEnvelope(id,if(row.outgoing) service.account else row.peer,if(row.outgoing) row.peer else service.account,time,1,byteArrayOf(1))
                        val kind=if(row.outgoing) "outgoing" else "incoming"
                        vault.put(kind,id.toString(),StoredChat(envelope,row.text,"delivered",row.unread==0).encode())
                        ConversationHistory.record(vault,kind,id,row.peer,time,unread=row.unread>0)
                        if(row.peer==service.peer)service.generatedPeerReplies[id]=row.text
                    }
                }
            }
        }
    }
}
