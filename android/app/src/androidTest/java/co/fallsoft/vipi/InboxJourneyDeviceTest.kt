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
        MainActivityJourneyFixture("settings-previews", { app ->
            // Earlier versions stored both “off” and “never set” as an absent token.
            MessageVault(app, service.account).use { it.transaction { it.remove("local", "notification-previews") } }
            seed(app, service, listOf(incoming)); service.model(app)
        }).use { f ->
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithTag("inbox-enable-previews").assertDoesNotExist()
                compose.onNodeWithText(f.base.getString(R.string.settings_message_previews)).assertDoesNotExist()
                compose.onNodeWithText(f.base.getString(R.string.notification_reply_later)).assertDoesNotExist()
                paint(f, "inbox-without-preview-offer")
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick()
                screen(f, Screen.SETTINGS)
                compose.onAllNodesWithText(f.base.getString(R.string.settings_title)).assertCountEquals(1)
                paint(f, "settings-profile-and-chats")
                val toggle = compose.onNodeWithTag("settings-message-previews")
                toggle.performScrollTo().assertIsOff().assertTextContains(f.base.getString(R.string.settings_message_previews))
                val generic = f.base.getString(R.string.ui_3abeae7a3bed)
                fun notification(unlocked: Boolean) = PushDelivery.buildNotifications(f.base, f.model.chat!!, unlocked).single().notification
                fun body(note: android.app.Notification) = note.extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString()
                compose.runOnIdle { assertEquals(generic, body(notification(true))) }
                compose.onNodeWithText(generic).performScrollTo(); paint(f, "settings-preview-private")
                toggle.performScrollTo().performClick().assertIsOn()
                compose.onNodeWithText(f.base.getString(R.string.settings_sample_message)).performScrollTo(); paint(f, "settings-preview-content")
                compose.runOnIdle { assertEquals("Opting in does not reveal older history", generic, body(notification(true))) }
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
                    val chat = requireNotNull(f.model.chat)
                    chat.send("I am reading a book now.", service.peer)
                    chat.synchronize()
                    require(service.peerReceived == "I am reading a book now.")
                    service.queueAdditionalPeerReplyAndSignalInbox("New reply after consent")
                }
                compose.waitUntil(15_000) { service.friendReplyReceipts.get() == 1 }
                compose.runOnIdle {
                    assertTrue("A preview never marked the message read", service.seenMessages.isEmpty())
                    val privateNote = notification(true)
                    assertEquals("New reply after consent", body(privateNote)); assertEquals("Maya", privateNote.extras.getString(android.app.Notification.EXTRA_TITLE))
                    assertEquals(android.app.Notification.VISIBILITY_PRIVATE, privateNote.visibility)
                    assertEquals(generic, body(privateNote.publicVersion)); assertEquals(generic, body(notification(false)))
                }
                f.relaunch(service::model); screen(f, Screen.HOME)
                compose.runOnIdle {
                    assertTrue(f.model.chat!!.notificationPreviews)
                    assertEquals("New reply after consent", body(notification(true)))
                    f.model.chat!!.markRead(service.peer)
                    assertTrue(PushDelivery.buildNotifications(f.base, f.model.chat!!, true).isEmpty())
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
    @Test fun headerActionsFitTogetherAndKeepTheirStateAndIdentity() {
        val args = androidx.test.platform.app.InstrumentationRegistry.getArguments()
        val longName = args.getString("vipiLongName") == "true"
        val name = if (longName) "Alexandra del Castillo Fernández" else "Maya"
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = name,
            translationFactory = { object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String) = when (text) {
                    "See you at six?" -> "¿Nos vemos a las seis?"
                    else -> text
                }
                override fun close() = Unit
            } })
        val incoming = Row(service.peer, name, "See you at six?", System.currentTimeMillis())
        MainActivityJourneyFixture("adaptive-header", { app -> seed(app, service, listOf(incoming)); service.model(app) }).use { f ->
            try {
                compose.runOnIdle { f.model.selectTarget("es"); f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES) }
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithTag("inbox-row-${service.peer}").performClick(); screen(f, Screen.CONVERSATION)
                val autoplay = compose.onNodeWithTag("conversation-autoplay")
                val mode = compose.onNodeWithTag("conversation-immersion")
                val contact = compose.onNodeWithTag("conversation-contact")
                val options = compose.onNodeWithTag("conversation-options")
                val originalMode = f.model.immersionMode
                fun bounds(node: SemanticsNodeInteraction) = node.fetchSemanticsNode().boundsInWindow
                val before = listOf(contact, autoplay, mode, options).map(::bounds)
                val density = f.base.resources.displayMetrics.density
                val labelled = args.getString("vipiHeaderLabels")?.toBooleanStrictOrNull()
                for (node in listOf(autoplay, mode)) {
                    val rect = bounds(node)
                    assertTrue("48dp minimum target on both axes", minOf(rect.width, rect.height) >= 48 * density - .5f)
                    if (labelled != null) assertEquals("Both labels fit or both use icons", labelled, rect.width > 48 * density + 1)
                    val semantics = node.fetchSemanticsNode().config
                    assertEquals(androidx.compose.ui.semantics.Role.Switch, semantics[SemanticsProperties.Role])
                    assertTrue(semantics[SemanticsProperties.StateDescription].isNotBlank())
                    assertFalse(semantics[androidx.compose.ui.semantics.SemanticsActions.OnClick].label.isNullOrBlank())
                }
                assertEquals(before[1].center.y, before[2].center.y, 1f)
                contact.assertTextEquals(name)
                autoplay.assertContentDescriptionEquals(f.base.getString(R.string.autoplay_label)).assertIsOff()
                mode.assertContentDescriptionEquals(f.base.getString(R.string.immersion_mode_title))
                compose.waitUntil(12_000) {
                    f.model.chat!!.translations?.state(incoming.id.toString(), incoming.text)?.phase == MessageTranslationPhase.READY
                }
                paint(f, "01-friend-header")
                val editor = compose.onNodeWithTag("message-input")
                editor.performTouchInput { click() }.performTextInput("My draft")
                autoplay.performTouchInput { click() }.assertIsOn()
                paint(f, "02-autoplay-on")
                mode.performTouchInput { click() }
                compose.waitUntil { f.model.immersionMode != originalMode }
                editor.assertIsFocused().assertTextEquals("My draft")
                paint(f, "03-friend-other-mode")
                assertEquals("Control and contact bounds stable across modes", before.map { it.left to it.right },
                    listOf(contact, autoplay, mode, options).map { bounds(it).let { r -> r.left to r.right } })
                compose.waitUntil(5_000) { f.unobscuredWindow().bottom < f.base.resources.displayMetrics.heightPixels * .86f }
                val geometry = JSONObject().put("locale", f.base.resources.configuration.locales[0].toLanguageTag())
                    .put("fontScale", f.base.resources.configuration.fontScale).put("density", density)
                    .put("longName", longName).put("bounds", JSONArray(before.map { it.toString() }))
                File(f.output, "geometry.json").writeText(geometry.toString(2))
            } finally { f.stopActivity(); service.close() }
        }
    }

    @Test fun headerPracticeChooserStaysAccessibleWithLocalizedLargeText() {
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        MainActivityJourneyFixture("localized-practice", service::model).use { f ->
            try {
                compose.runOnIdle { f.model.selectTarget("zh") }
                f.launch(); screen(f, Screen.HOME)
                val practice = compose.onNodeWithTag("inbox-practice-language")
                practice.assertIsDisplayed().assertContentDescriptionEquals(f.base.getString(R.string.chats_practice_language))
                val bounds = practice.fetchSemanticsNode().boundsInWindow
                assertTrue(minOf(bounds.width, bounds.height) >= 48 * f.base.resources.displayMetrics.density - 1)
                practice.performTouchInput { click() }
                val same = compose.onNodeWithText("中文", substring = true)
                same.assertIsSelected()
                paint(f, "01-open-selected")
                compose.onNodeWithText("Português", substring = true).performScrollTo().performClick()
                compose.waitUntil { f.model.targetLanguage == "pt" }
                assertEquals("en", f.model.knownLanguage)
                paint(f, "02-chats-retargeted")
                val state = practice.fetchSemanticsNode().config[SemanticsProperties.StateDescription]
                assertTrue(java.util.Locale.forLanguageTag("pt").getDisplayLanguage(f.base.resources.configuration.locales[0]).equals(state, ignoreCase = true))
            } finally { f.stopActivity(); service.close() }
        }
    }
    @Test fun practiceLanguageAndAutoplayFollowTheirActualOwners() {
        val prompt = "Can we meet at six?"
        val spanish = "¿Nos vemos a las seis?"
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya",
            translationFactory = { object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String) =
                    when (text) { prompt -> spanish; "I’ll bring the coffee." -> "Llevaré el café."; else -> text }
                override fun close() = Unit
            } })
        val initial = Row(service.peer, "Maya", prompt, System.currentTimeMillis() - 60_000)
        val events = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        MainActivityJourneyFixture("chat-header", { app -> seed(app, service, listOf(initial)); service.model(app) }).use { f ->
            MessageAudioQualification.attach { events += it }
            try {
                compose.runOnIdle { f.model.selectTarget("zh"); f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES) }
                f.launch(); screen(f, Screen.HOME)
                val practice = compose.onNodeWithTag("inbox-practice-language")
                fun assertLanguage(name: String) {
                    practice.assertContentDescriptionEquals(f.base.getString(R.string.chats_practice_language))
                    assertEquals(name, practice.fetchSemanticsNode().config[SemanticsProperties.StateDescription])
                }
                assertLanguage("Chinese")
                practice.performClick()
                compose.onNodeWithText("Chinese · 中文").assertIsSelected()
                compose.onNodeWithText("English · English").assertDoesNotExist()
                paint(f, "00-language-chooser")
                f.device.pressBack()
                assertEquals("zh", f.model.targetLanguage); assertLanguage("Chinese")
                practice.performClick()
                compose.onNodeWithText("Spanish · Español").performClick()
                compose.waitUntil { f.model.targetLanguage == "es" }
                assertEquals("en", f.model.knownLanguage)
                assertLanguage("Spanish")
                paint(f, "01-inbox-spanish")
                compose.onNodeWithTag("inbox-row-${service.peer}").performClick()
                screen(f, Screen.CONVERSATION)
                val autoplay = compose.onNodeWithTag("conversation-autoplay")
                val mode = compose.onNodeWithTag("conversation-immersion")
                val editor = compose.onNodeWithTag("message-input")
                autoplay.assertIsDisplayed().assertIsOff(); mode.assertIsDisplayed().assertIsOn()
                val bounds = autoplay.fetchSemanticsNode().boundsInWindow
                assertTrue(bounds.height >= 48 * f.base.resources.displayMetrics.density)
                paint(f, "02-autoplay-off")
                compose.waitUntil(30_000) { f.model.chat!!.translations?.state(initial.id.toString(), prompt)?.phase == MessageTranslationPhase.READY }
                compose.runOnIdle { check(f.paragraphs().single { it.originalMessage == prompt }
                    .performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK, null)) }
                fun completed(id: String) = events.any { it.optString("id") == id && it.optString("stage") == "pcm_completed" }
                compose.waitUntil(45_000) { completed(initial.id.toString()) }
                editor.performTouchInput { click() }.performTextInput("I’ll bring the coffee.")
                compose.onNodeWithTag("message-send").performClick()
                compose.waitUntil(15_000) { service.peerReceived == "I’ll bring the coffee." }
                editor.performTouchInput { click() }.performTextInput("See you soon")
                compose.waitUntil(8_000) { f.unobscuredWindow().bottom < f.base.resources.displayMetrics.heightPixels * .86f }
                autoplay.performTouchInput { click() }.assertIsOn()
                editor.assertIsFocused().assertTextContains("See you soon")
                mode.assertIsOn()
                var arrival: UUID? = null
                compose.runOnIdle { arrival = service.queueAdditionalPeerReplyAndSignalInbox(prompt) }
                compose.waitUntil(45_000) { completed(requireNotNull(arrival).toString()) }
                assertTrue(events.filter { it.optString("stage") == "translation_ready" }.all { it.getString("practice_language") == "es" })
                assertEquals(listOf(false, true), events.filter { it.optString("stage") == "translation_ready" }.map { it.getBoolean("automatic") })
                assertTrue(events.filter { it.optString("stage") == "speech_request" }.all { it.getString("practice_text") == spanish })
                paint(f, "03-autoplay-on-typing")
                autoplay.performTouchInput { click() }.assertIsOff()
                editor.assertIsFocused().assertTextContains("See you soon")
                f.device.pressBack()
                compose.waitUntil(8_000) { f.unobscuredWindow().bottom > f.base.resources.displayMetrics.heightPixels * .86f }
                f.device.pressBack(); screen(f, Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performClick()
                compose.onNodeWithText(f.base.getString(R.string.ui_e7cde359a05e)).performScrollTo().performClick()
                compose.onNodeWithContentDescription(f.base.getString(R.string.want_learn)).performScrollTo().performClick()
                compose.onNodeWithText("Portuguese · Português").performScrollTo().performClick()
                compose.waitUntil { f.model.targetLanguage == "pt" }
                val back = compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back))
                back.performScrollTo().performClick(); screen(f, Screen.SETTINGS)
                back.performScrollTo().performClick(); screen(f, Screen.HOME)
                assertLanguage("Portuguese")
                paint(f, "04-inbox-portuguese")
                f.relaunch(service::model); screen(f, Screen.HOME)
                assertLanguage("Portuguese")
                compose.onNodeWithTag("inbox-row-${service.peer}").performClick()
                screen(f, Screen.CONVERSATION); autoplay.assertIsOff()
                editor.assertTextContains("See you soon"); mode.assertIsOn()
                File(f.output, "speech-events.json").writeText(JSONArray(events).toString(2))
            } finally { MessageAudioQualification.attach(null); f.stopActivity(); service.close() }
        }
    }

    @Test fun realShadeShowsSeparatePrivateRepliesAndEachTapOpensItsFriend() {
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        val second = UUID.randomUUID()
        val firstText = "The train leaves at six."
        val nextText = "I'll meet you at the station."
        val otherText = "Dinner is ready."
        val freshMaya = "I’ll bring the tickets."
        val now = System.currentTimeMillis()
        MainActivityJourneyFixture("notification-shade", { app ->
            seed(app, service, listOf(Row(service.peer, "Maya", firstText, now, unread = 1),
                Row(second, "Sam", "See you soon", now - 30_000)))
            service.model(app)
        }).use { f ->
            val manager = f.base.getSystemService(android.app.NotificationManager::class.java)
            val device = f.device
            fun notes() = manager.activeNotifications.filter { it.notification.channelId == PushDelivery.CHANNEL }
            fun show(text: String) = check(device.wait(androidx.test.uiautomator.Until.hasObject(androidx.test.uiautomator.By.text(text)), 8_000))
            fun capture(name: String) {
                device.waitForIdle()
                check(device.takeScreenshot(File(f.output, "$name.png")))
                device.dumpWindowHierarchy(File(f.output, "$name.xml"))
            }
            fun home() {
                check(device.pressHome())
                compose.waitUntil(8_000) { !androidx.lifecycle.ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED) }
            }
            fun notify() = f.instrumentation.runOnMainSync { PushDelivery.notify(f.base, requireNotNull(f.model.chat)) }
            try {
                device.executeShellCommand("pm grant ${f.base.packageName} android.permission.POST_NOTIFICATIONS")
                f.launch(); screen(f, Screen.HOME)
                val chat = requireNotNull(f.model.chat)
                assertTrue(chat.notificationPreviews)
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
                    chat.send("See you there.", service.peer); chat.synchronize()
                    check(service.peerReceived == "See you there.")
                }
                home()
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
                    service.queueAdditionalPeerReplyAndSignalInbox(nextText, wakeForeground = false)
                    chat.synchronize()
                }
                assertEquals(1, service.friendReplyReceipts.get())
                notify()
                compose.waitUntil(8_000) { notes().size == 1 }
                check(device.openNotification()); show(nextText); capture("01-one-friend")
                device.pressBack()
                notes().single().let { manager.cancel(it.tag, it.id) }
                compose.waitUntil(5_000) { notes().isEmpty() }
                notify(); android.os.SystemClock.sleep(250)
                assertTrue("Duplicate notification wake must respect dismissal", notes().isEmpty())
                f.instrumentation.runOnMainSync {
                    seed(f.model.getApplication(), service, listOf(Row(second, "Sam", otherText, now + 10_000, unread = 1)))
                }
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) { chat.synchronize() }
                notify(); compose.waitUntil(8_000) { notes().size == 1 }
                assertEquals(otherText, notes().single().notification.extras.getCharSequence(android.app.Notification.EXTRA_TEXT))
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
                    service.queueAdditionalPeerReplyAndSignalInbox(freshMaya, wakeForeground = false); chat.synchronize()
                }
                notify(); compose.waitUntil(8_000) { notes().size == 2 }
                check(device.openNotification()); show(freshMaya); show(otherText); capture("02-two-friends")
                val generic = f.base.getString(R.string.ui_3abeae7a3bed)
                f.instrumentation.runOnMainSync {
                    for (note in PushDelivery.buildNotifications(f.base, chat, true)) {
                        assertEquals(android.app.Notification.VISIBILITY_PRIVATE, note.notification.visibility)
                        assertEquals(generic, note.notification.publicVersion.extras.getCharSequence(android.app.Notification.EXTRA_TEXT))
                    }
                    assertEquals(generic, PushDelivery.buildNotifications(f.base, chat, false).single().notification.extras.getCharSequence(android.app.Notification.EXTRA_TEXT))
                }
                val expand = device.findObject(androidx.test.uiautomator.By.res("com.android.systemui", "expand_button"))
                if (device.hasObject(androidx.test.uiautomator.By.text("2")) && expand != null) {
                    expand.click(); show(otherText); capture("02b-two-friends-expanded")
                }
                device.findObject(androidx.test.uiautomator.By.text(otherText)).click()
                screen(f, Screen.CONVERSATION); assertEquals(second, f.model.selectedPeer)
                compose.waitUntil(5_000) { notes().size == 1 }
                f.capture("03-sam-opened")
                check(device.openNotification()); show(freshMaya)
                device.findObject(androidx.test.uiautomator.By.text(freshMaya)).click()
                compose.waitUntil(8_000) { f.model.selectedPeer == service.peer }
                compose.waitUntil(5_000) { notes().isEmpty() }
                f.capture("04-maya-opened")
                // An explicit OFF must redact even future deliveries and cancel
                // existing shade content without reusing the previous consent.
                f.instrumentation.runOnMainSync { chat.changeNotificationPreviews(false) }
                home()
                kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
                    service.queueAdditionalPeerReplyAndSignalInbox("Hidden after opting out.", wakeForeground = false); chat.synchronize()
                }
                notify(); compose.waitUntil(8_000) { notes().size == 1 }
                check(device.openNotification()); show(generic); capture("05-previews-off")
                assertFalse(device.hasObject(androidx.test.uiautomator.By.text("Hidden after opting out.")))
                device.pressBack()
                f.instrumentation.runOnMainSync { f.model.authentication.signOutLocally() }
                compose.waitUntil(5_000) { notes().isEmpty() }
                File(f.output, "verified.json").writeText(JSONObject().put("actualSystemShade", true)
                    .put("singleAndMultiTap", true).put("opaqueExternalPushTransportSimulated", true)
                    .put("privatePublicVersion", true).put("signoutCleared", true).toString())
            } finally { PushDelivery.clearPosted(f.base); f.finishAfterExternalIntent(); service.close() }
        }
    }

    @Test fun lockedEmulatorRedactsPostedReplyAndSignoutRemovesIt() {
        val service = JourneyServices(profileRequired = false)
        val body = "A private message for the unlocked screen."
        MainActivityJourneyFixture("notification-lock", { app ->
            seed(app, service, listOf(Row(service.peer, "Maya", body, System.currentTimeMillis(), unread = 1)))
            service.model(app)
        }).use { f ->
            val device = f.device
            val keyguard = f.base.getSystemService(android.app.KeyguardManager::class.java)
            val manager = f.base.getSystemService(android.app.NotificationManager::class.java)
            check(!keyguard.isDeviceSecure)
            val settings = listOf("lock_screen_show_notifications", "lock_screen_allow_private_notifications", "lock_screen_lock_after_timeout")
            val original = settings.associateWith { device.executeShellCommand("settings get secure $it").trim() }
            val wasDisabled = device.executeShellCommand("locksettings get-disabled").trim()
            val pin = "781534" // ephemeral owned emulator only
            try {
                device.executeShellCommand("pm grant ${f.base.packageName} android.permission.POST_NOTIFICATIONS")
                check(device.executeShellCommand("locksettings set-pin $pin").contains("set to"))
                device.executeShellCommand("settings put secure lock_screen_show_notifications 1")
                device.executeShellCommand("settings put secure lock_screen_allow_private_notifications 0")
                device.executeShellCommand("settings put secure lock_screen_lock_after_timeout 0")
                f.launch(); screen(f, Screen.HOME)
                device.pressHome()
                compose.waitUntil(8_000) { !androidx.lifecycle.ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED) }
                f.instrumentation.runOnMainSync { PushDelivery.notify(f.base, f.model.chat!!) }
                compose.waitUntil(8_000) { manager.activeNotifications.any { it.notification.extras.getCharSequence(android.app.Notification.EXTRA_TEXT) == body } }
                device.sleep(); android.os.SystemClock.sleep(750); device.wakeUp()
                compose.waitUntil(8_000) { keyguard.isDeviceLocked }
                device.openNotification(); device.waitForIdle()
                check(device.takeScreenshot(File(f.output, "01-secure-keyguard.png")))
                device.dumpWindowHierarchy(File(f.output, "01-secure-keyguard.xml"))
                assertFalse(device.hasObject(androidx.test.uiautomator.By.text(body)))
                assertFalse(device.hasObject(androidx.test.uiautomator.By.text("Maya")))
                f.instrumentation.runOnMainSync { f.model.authentication.signOutLocally() }
                compose.waitUntil(5_000) { manager.activeNotifications.none { it.notification.channelId == PushDelivery.CHANNEL } }
                File(f.output, "verified.json").writeText(JSONObject().put("isDeviceLocked", keyguard.isDeviceLocked)
                    .put("hideSensitiveContent", true).put("noSenderOrMessageInLockscreen", true).put("signoutRemovedAlert", true).toString())
            } finally {
                device.executeShellCommand("locksettings clear --old $pin")
                device.executeShellCommand("wm dismiss-keyguard")
                if (wasDisabled in setOf("true", "false")) device.executeShellCommand("locksettings set-disabled $wasDisabled")
                original.forEach { (key, value) -> device.executeShellCommand(if (value == "null") "settings delete secure $key" else "settings put secure $key $value") }
                device.sleep(); android.os.SystemClock.sleep(400); device.wakeUp()
                device.executeShellCommand("wm dismiss-keyguard")
                PushDelivery.clearPosted(f.base); f.stopActivity(); service.close()
            }
        }
    }

    @Test fun suppressesUnsafeAndHistoricalAlertsAndErasesThePostedCard() {
        val service = JourneyServices(profileRequired = false)
        val now = System.currentTimeMillis()
        val peers = (0..4).map { UUID.randomUUID() }
        val rows = peers.mapIndexed { i, peer -> Row(peer, "Contact $i", "Private fixture $i", now - i * 1000L, unread = 1) }
        MainActivityJourneyFixture("notification-eligibility", { app ->
            seed(app, service, rows)
            MessageVault(app, service.account).use { v -> v.transaction {
                v.put("blocked", peers[1].toString(), byteArrayOf(1))
                v.put("peer-recovery-needed", peers[2].toString(), byteArrayOf(1))
                val k = peers[3].toString()
                val summary = JSONObject(requireNotNull(v.get("thread", k)).toString(Charsets.UTF_8))
                summary.remove("notificationDeliveryTracked")
                v.put("thread", k, summary.toString().toByteArray())
            } }
            service.model(app)
        }).use { f ->
            val manager = f.base.getSystemService(android.app.NotificationManager::class.java)
            try {
                f.device.executeShellCommand("pm grant ${f.base.packageName} android.permission.POST_NOTIFICATIONS")
                f.launch(); screen(f, Screen.HOME)
                val chat = requireNotNull(f.model.chat)
                compose.runOnIdle {
                    MessageVault(f.model.getApplication(), service.account).use { v -> v.transaction {
                        v.remove("incoming", rows[4].id.toString())
                    } }
                    val alerts = PushDelivery.buildNotifications(f.base, chat, true)
                    assertEquals(listOf(rows[0].text), alerts.map { it.notification.extras.getCharSequence(android.app.Notification.EXTRA_TEXT) })
                    f.model.openNotification(peers[0].toString(), "different-account")
                    assertEquals(Screen.HOME, f.model.screen)
                }
                f.device.pressHome()
                compose.waitUntil(5_000) { !androidx.lifecycle.ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED) }
                f.instrumentation.runOnMainSync { PushDelivery.notify(f.base, chat) }
                compose.waitUntil(5_000) { manager.activeNotifications.any { it.notification.channelId == PushDelivery.CHANNEL } }
                val app: Application = f.model.getApplication()
                f.stopActivity()
                AccountDeletion.eraseLocal(app, DeletionRecord(service.account, chat.userID, "synthetic", now))
                compose.waitUntil(5_000) { manager.activeNotifications.none { it.notification.channelId == PushDelivery.CHANNEL } }
                assertFalse(File(app.noBackupFilesDir, "messages/${service.account}").exists())
            } finally { PushDelivery.clearPosted(f.base); f.stopActivity(); service.close() }
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
