package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual MainActivity visual review captures, with local controlled transport
 * and Play SDK boundaries. Screenshots require independent human/product review;
 * this test does not turn bounds or message counts into visual acceptance. */
class VisualHierarchyJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private fun screen(f: MainActivityJourneyFixture, value: Screen) = compose.waitUntil(10_000) { f.model.screen == value }
    private fun back(f: MainActivityJourneyFixture, value: Screen) { f.device.pressBack(); screen(f, value) }
    private fun ime(f: MainActivityJourneyFixture): Boolean {
        var shown = false
        f.instrumentation.runOnMainSync {
            shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                view.rootWindowInsets?.let { androidx.core.view.WindowInsetsCompat.toWindowInsetsCompat(it)
                    .isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) } == true
            }
        }
        return shown
    }
    private fun click(text: String) = compose.onNodeWithText(text).performScrollTo().performTouchInput { click() }

    @Test fun actualHomeReconnectEmptyPopulatedFriendAndBotShareOneConversationHierarchy() {
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 2)
        services.profileUnavailable.set(true)
        MainActivityJourneyFixture("visual-hierarchy", services::model).use { f ->
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.waitUntil(8_000) { f.model.chat?.busy == false && f.model.chat?.notice != null }
                compose.onNodeWithText(f.base.getString(R.string.nav_chats)).assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.ui_d8b8392e2c54)).assertIsDisplayed()
                f.capture("01-home-reconnect-with-existing-action")
                services.profileUnavailable.set(false)
                click(f.base.getString(R.string.ui_d8b8392e2c54))
                compose.waitUntil(10_000) { f.model.chat?.ready == true }
                compose.onNodeWithText(f.base.getString(R.string.ui_f173182378d0)).assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.ui_258150cb3ee4)).assertIsDisplayed()
                f.capture("02-home-empty-single-header-and-bot-row")
                click(f.base.getString(R.string.ui_258150cb3ee4)); screen(f, Screen.NEW_CHAT)
                val username = compose.onNode(hasSetTextAction())
                username.performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { ime(f) }
                username.performTextInput("@Journey_Friend")
                username.assert(SemanticsMatcher("Exact native lookup text before keyboard dismissal") {
                    it.config[androidx.compose.ui.semantics.SemanticsProperties.EditableText].text == "@Journey_Friend"
                }).assertIsFocused()
                f.tapNativeGboardSearch(compose, "02a-native-keyboard-search-action")
                screen(f, Screen.CONVERSATION)
                compose.runOnIdle { assertEquals(listOf("journey_friend"), services.lookups) }
                compose.onNodeWithTag("message-input").performTextInput("I am reading a book now.")
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(8_000) { services.friendPosts.get() == 1 && f.model.chat?.messages(services.peer)?.singleOrNull()?.state == "delivered" }
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(8_000) { f.model.chat?.messages(services.peer)?.size == 2 && services.friendReplyReceipts.get() == 1 }
                f.device.pressBack() // dismiss the native IME, if present
                compose.waitForIdle()
                if (f.model.screen != Screen.CONVERSATION) {
                    click("Journey Friend"); screen(f, Screen.CONVERSATION)
                }
                f.capture("03-friend-same-book-prompt-cafe-reply-without-ime")
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.onNodeWithTag("message-input").performTextInput("Keep this next friend message local.")
                f.assertIncomingAboveComposer(compose, services.friendReply, "04-friend-reply-and-editable-next-draft")
                f.device.pressBack(); compose.waitForIdle()
                back(f, Screen.HOME)
                compose.onNodeWithText("Journey Friend").assertIsDisplayed()
                f.capture("05-home-populated-thread-and-bot-row")
                click(f.base.getString(R.string.ui_f173182378d0)); screen(f, Screen.BOT)
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.bot?.allowance != null && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.runOnIdle { services.botReplyGate.complete(Unit) }
                listOf("A local Bot lifecycle greeting.", "Keep the next turn in this conversation.").forEachIndexed { index, prompt ->
                    compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                    compose.onNodeWithTag("bot-message-input").performTextInput(prompt)
                    compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                    compose.waitUntil(8_000) { services.botPosts.get() == index + 1 && f.model.bot?.busy == false && f.model.bot?.messages?.size == (index + 1) * 2 }
                }
                f.device.pressBack(); compose.waitForIdle()
                if (f.model.screen != Screen.BOT) { click(f.base.getString(R.string.ui_f173182378d0)); screen(f, Screen.BOT) }
                f.capture("06-bot-four-turns-same-lifecycle-replies-without-ime")
                compose.onNodeWithText(f.base.getString(R.string.ui_ff245b368781)).performTouchInput { click() }; screen(f, Screen.BOT_PLAN)
                compose.onNodeWithText("148 of 150 replies left", substring = true).performScrollTo().assertIsDisplayed()
                f.capture("07-healthy-usage-in-existing-bot-mini-details")
                back(f, Screen.BOT)
                services.assertNoPurchase()
                File(f.output, "receipt.json").writeText(JSONObject().put("actual_main_activity", true)
                    .put("controlled_profile_network_failure_and_actual_retry", true).put("real_signal_friend_exchange", true)
                    .put("bot_posts", services.botPosts.get()).put("friend_posts", services.friendPosts.get())
                    .put("billing_launches", 0).put("visual_review_required", true).toString(2))
            } catch (failure: Throwable) {
                File(f.output, "failure-controlled-state.json").writeText(JSONObject()
                    .put("bot_posts", services.botPosts.get()).put("accepted_request_contexts", org.json.JSONArray(services.botRequestPrompts))
                    .put("real_bot_busy", f.model.bot?.busy).put("real_bot_notice", f.model.bot?.notice)
                    .put("real_bot_messages", org.json.JSONArray(f.model.bot?.messages?.map { it.json() }.orEmpty())).toString(2))
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }; throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }

    @Test fun actualEndedMonthPlansGroupsUnavailablePriceRestoreAndNoEnrollmentContext() {
        val services = JourneyServices(profileRequired = false, cardlessAccess = true, emptyPriceCatalog = true)
        services.baseExpired.set(true)
        MainActivityJourneyFixture("visual-plans-unavailable", services::model).use { f ->
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.waitUntil(8_000) { f.model.chat?.ready == true }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performTouchInput { click() }
                screen(f, Screen.SETTINGS)
                click(f.base.getString(R.string.nav_plan)); screen(f, Screen.PLANS)
                compose.waitUntil(8_000) { f.model.subscriptions?.busy == false && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.onNodeWithText(f.base.getString(R.string.ui_3ceeccf6b3ff)).assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.ui_8927db75ddd0)).assertIsDisplayed()
                compose.runOnIdle { assertTrue(f.model.subscriptions!!.offers.isEmpty()); assertFalse(f.model.subscriptions!!.access!!.active(SubscriptionPlan.BASE)); services.assertNoPurchase() }
                f.capture("01-ended-month-price-unavailable-and-existing-restore")
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }; throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }
}
