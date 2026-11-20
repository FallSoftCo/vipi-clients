package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.test.platform.app.InstrumentationRegistry
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
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

    /** Controlled account/catalog states, actual production navigation and paint.
     * Run separately at recorded OS font1/font2; no model or purchase proof. */
    @Test fun actualAccessStatesCatalogAndSettingsAtRecordedSystemFont() {
        val font = requireNotNull(InstrumentationRegistry.getArguments().getString("vipiReviewFontScale")).toFloat()
        require(font in setOf(1f, 2f))
        for (state in listOf("active", "expired", "bot", "empty", "loading")) {
            val expired = state in setOf("expired", "empty", "loading")
            val services = JourneyServices(profileRequired = false, cardlessAccess = true,
                emptyPriceCatalog = state == "empty", holdPriceCatalog = state == "loading",
                cardlessStartedAt = Instant.now().minusSeconds((if (expired) 31 else 1) * 86_400L),
                accountDisplayName = "Alex", peerDisplayName = "Maya")
            services.baseExpired.set(expired)
            MainActivityJourneyFixture("plan-review-$state", { app -> services.model(app).apply { selectTarget("zh") } }).use { f ->
                val observations = org.json.JSONArray()
                val gesturePreferences = f.base.getSharedPreferences("full-message-gestures", android.content.Context.MODE_PRIVATE)
                val hadGesturePolicy = gesturePreferences.contains("hold-script-policy-1")
                val gesturePolicy = gesturePreferences.getBoolean("hold-script-policy-1", false)
                fun observe(name:String) {
                    val texts = compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text), useUnmergedTree = true)
                        .fetchSemanticsNodes().map { node -> JSONObject()
                            .put("text", node.config[SemanticsProperties.Text].joinToString(" ") { it.text })
                            .put("visible_window_bounds", node.boundsInWindow.toString()) }
                    val subscriptions = requireNotNull(f.model.subscriptions)
                    observations.put(JSONObject().put("name",name).put("screen",f.model.screen.name)
                        .put("font_scale",f.base.resources.configuration.fontScale.toDouble())
                        .put("busy",subscriptions.busy).put("access_state",subscriptions.accessCheckState.name)
                        .put("base_source",subscriptions.access?.base?.accessSource ?: JSONObject.NULL)
                        .put("offer_count",subscriptions.offers.size).put("notice",subscriptions.notice ?: JSONObject.NULL)
                        .put("unobscured_window",f.unobscuredWindow().toShortString()).put("texts",org.json.JSONArray(texts)))
                    File(f.output,"observations.json").writeText(observations.toString(2))
                }
                fun capture(name:String) { compose.waitForIdle(); observe(name+"-before"); f.capture(name); observe(name+"-after") }
                fun completeTarget(node:SemanticsNodeInteraction, enabled:Boolean = true) {
                    node.performScrollTo().assertIsDisplayed().assertHasClickAction()
                    val touch = node.fetchSemanticsNode().touchBoundsInRoot
                    val minimum = 48 * f.base.resources.displayMetrics.density
                    observations.put(JSONObject().put("target_touch_bounds_in_root",touch.toString()).put("required_px",minimum))
                    File(f.output,"observations.json").writeText(observations.toString(2))
                    assertTrue("Actual expanded click height $touch must be48dp",touch.height >= minimum)
                    assertTrue("Actual expanded click width $touch must be48dp",touch.width >= minimum)
                    if (enabled) node.assertIsEnabled() else node.assertIsNotEnabled()
                    val full = node.getUnclippedBoundsInRoot(); val visible = node.getBoundsInRoot()
                    val pixel = 1f / f.base.resources.displayMetrics.density
                    assertEquals("Complete target left",full.left.value,visible.left.value,pixel)
                    assertEquals("Complete target top",full.top.value,visible.top.value,pixel)
                    assertEquals("Complete target right",full.right.value,visible.right.value,pixel)
                    assertEquals("Complete target bottom",full.bottom.value,visible.bottom.value,pixel)
                }
                try {
                    f.launch(); screen(f,Screen.HOME)
                    compose.waitUntil(10_000) { f.model.chat?.ready == true &&
                        f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                    assertEquals("Actual OS text size, not a synthetic density wrapper",font,f.base.resources.configuration.fontScale,0.01f)
                    if (state == "active") {
                        compose.onNodeWithText(f.base.getString(R.string.nav_chats)).assertIsDisplayed()
                        capture("01-empty-home")
                    }
                    if (state == "bot") {
                        click(f.base.getString(R.string.ui_f173182378d0)); screen(f,Screen.BOT)
                        compose.onNodeWithText(f.base.getString(R.string.ui_ff245b368781)).performTouchInput { click() }
                        screen(f,Screen.BOT_PLAN)
                    } else {
                        compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performTouchInput { click() }
                        screen(f,Screen.SETTINGS)
                        compose.onNodeWithText(f.base.getString(R.string.settings_title)).performScrollTo().assertIsDisplayed()
                        if (state == "active") {
                            capture("02-settings-entry")
                            click(f.base.getString(R.string.appearance_dark))
                            compose.runOnIdle { assertEquals(Appearance.DARK,f.model.appearance) }
                            capture("03-settings-dark")
                            click(f.base.getString(R.string.appearance_light))
                            compose.runOnIdle { assertEquals(Appearance.LIGHT,f.model.appearance) }
                            click(f.base.getString(R.string.ui_2a6b4d12ccfb)); screen(f,Screen.LICENSES)
                            val loading = SemanticsMatcher.expectValue(SemanticsProperties.ProgressBarRangeInfo,
                                androidx.compose.ui.semantics.ProgressBarRangeInfo.Indeterminate)
                            compose.waitUntil(8_000) {
                                compose.onAllNodes(hasScrollToIndexAction()).fetchSemanticsNodes().size == 1 &&
                                    compose.onAllNodes(loading).fetchSemanticsNodes().isEmpty()
                            }
                            compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText("Vipi client · AGPL-3.0-only"))
                            val catalogEntry = compose.onNodeWithText("Vipi client · AGPL-3.0-only")
                            val catalogBounds = catalogEntry.fetchSemanticsNode().boundsInWindow
                            capture("03-before-client-license-catalog-anchor")
                            catalogEntry.performTouchInput { click() }
                            compose.waitUntil(8_000) {
                                compose.onAllNodesWithText(f.base.getString(R.string.ui_c011d6097bfb)).fetchSemanticsNodes().size == 1 &&
                                    compose.onAllNodes(loading).fetchSemanticsNodes().isEmpty()
                            }
                            capture("03a-client-license-readable-type")
                            compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasTestTag("licenses-client-source"))
                            completeTarget(compose.onNodeWithTag("licenses-client-source"))
                            capture("03b-short-source-link-complete-target")
                            f.device.pressBack(); compose.waitForIdle()
                            compose.waitUntil(8_000) {
                                compose.onAllNodesWithText(f.base.getString(R.string.ui_2a6b4d12ccfb)).fetchSemanticsNodes().size == 1 &&
                                    compose.onAllNodesWithText("Vipi client · AGPL-3.0-only").fetchSemanticsNodes().size == 1
                            }
                            val returnedCatalogBounds = catalogEntry.assertIsDisplayed().fetchSemanticsNode().boundsInWindow
                            assertEquals("Same selected catalog row left",catalogBounds.left,returnedCatalogBounds.left,1f)
                            assertEquals("Same selected catalog row top",catalogBounds.top,returnedCatalogBounds.top,1f)
                            assertEquals("Same selected catalog row right",catalogBounds.right,returnedCatalogBounds.right,1f)
                            assertEquals("Same selected catalog row bottom",catalogBounds.bottom,returnedCatalogBounds.bottom,1f)
                            capture("03-back-retains-client-license-catalog-anchor")
                            back(f,Screen.SETTINGS)
                            click(f.base.getString(R.string.ui_24f13e3dc8e4)); screen(f,Screen.BACKUP)
                            compose.onNodeWithText(f.base.getString(R.string.backup_intent)).assertIsDisplayed()
                            capture("03c-backup-form-first")
                            compose.onNodeWithText(f.base.getString(R.string.ui_04c8049b72ff)).performScrollTo().assertIsDisplayed()
                            completeTarget(compose.onNodeWithTag("backup-create"))
                            capture("03d-backup-recovery-warning-before-action")
                            compose.onNodeWithText(f.base.getString(R.string.ui_bb1fe2470e72)).performScrollTo().assertIsDisplayed()
                            capture("03e-backup-complete-scope-below-action")
                            back(f,Screen.SETTINGS)
                        }
                        click(f.base.getString(R.string.nav_plan)); screen(f,Screen.PLANS)
                    }
                    val subscriptions = requireNotNull(f.model.subscriptions)
                    if (state == "loading") {
                        compose.waitUntil(8_000) {
                            var pending = false
                            f.instrumentation.runOnMainSync { pending = services.priceQueryHeld() }
                            pending && subscriptions.busy
                        }
                        compose.onNodeWithText(f.base.getString(R.string.plan_prices_loading)).performScrollTo().assertIsDisplayed()
                        compose.onNodeWithText(f.base.getString(R.string.ui_8927db75ddd0)).assertDoesNotExist()
                        capture("04-prices-loading-not-unavailable")
                        compose.runOnIdle { assertTrue(services.priceQueryHeld()); services.releasePriceCatalog() }
                    }
                    compose.waitUntil(10_000) { !subscriptions.busy &&
                        (state == "empty" || subscriptions.offers.size == 2) }
                    compose.runOnIdle {
                        val base = requireNotNull(subscriptions.access).base
                        assertEquals(!expired,base.usable(requireNotNull(subscriptions.access).serverNow()))
                        assertEquals(!expired,base.cardlessTrial?.active)
                        if (!expired) assertEquals("cardless_trial",base.accessSource)
                    }
                    capture("05-$state-entry")
                    if (state == "active") {
                        val date = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG,FormatStyle.SHORT)
                            .withZone(ZoneId.systemDefault()).format(services.cardlessEnds)
                        compose.onNodeWithText(f.base.getString(R.string.cardless_ends,date)).assertExists()
                        compose.onNodeWithText(f.base.getString(R.string.cardless_no_autocharge)).performScrollTo().assertIsDisplayed()
                        val continueChat = compose.onNodeWithText(f.base.getString(R.string.ui_a2a2eed05c81))
                        completeTarget(continueChat); capture("06-free-access-no-automatic-charge")
                        continueChat.performTouchInput { click() }; screen(f,Screen.HOME)
                    } else if (state == "empty") {
                        assertTrue(subscriptions.offers.isEmpty())
                        compose.onNodeWithText(f.base.getString(R.string.ui_8927db75ddd0)).performScrollTo().assertIsDisplayed()
                        completeTarget(compose.onNodeWithText(f.base.getString(R.string.ui_3ceeccf6b3ff)))
                        capture("06-catalog-unavailable-with-recovery")
                    } else {
                        val plan = if (state == "bot") SubscriptionPlan.BOT_MINI else SubscriptionPlan.BASE
                        val offer = requireNotNull(subscriptions.offers[plan])
                        assertEquals(state == "bot",offer.oneMonthTrial)
                        val price = f.base.getString(if (offer.oneMonthTrial) R.string.trial_then_annual else R.string.annual_price,offer.annualPrice)
                        compose.onNodeWithText(price).performScrollTo().assertIsDisplayed()
                        val action = if (offer.oneMonthTrial) f.base.getString(R.string.ui_33a6e5e20062)
                            else f.base.getString(R.string.subscribe_annual, offer.annualPrice)
                        completeTarget(compose.onNodeWithText(action)); capture("06-$state-price-and-primary-action")
                        if (expired) compose.onNodeWithText(f.base.getString(R.string.ui_233a70befbdc)).performScrollTo().assertIsDisplayed()
                        if (state == "bot") {
                            compose.onNodeWithText(f.base.getString(R.string.ui_c518ff733bfe)).performScrollTo().assertIsDisplayed()
                            capture("07-bot-provider-and-friend-chat-scope")
                        }
                    }
                    assertEquals(0,services.friendPosts.get()); assertEquals(0,services.botPosts.get())
                    services.assertNoPurchase()
                    File(f.output,"review-scope.json").writeText(JSONObject().put("actual_main_activity",true)
                        .put("controlled_server_and_play_catalog",true).put("sdk_inference_claim",false)
                        .put("billing_launches",0).put("visual_review_required",true)
                        .put("actions_checked","Compose click action and actual expanded48dp touch bounds plus complete visual bounds; native XML retained; no TalkBack/purchase interaction claim")
                        .put("state",state).put("actual_os_font_scale",font.toDouble()).toString(2))
                } catch (failure:Throwable) {
                    runCatching { observe("failure"); f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                    throw failure
                } finally {
                    f.stopActivity(); services.close()
                    val edit = gesturePreferences.edit()
                    if (hadGesturePolicy) edit.putBoolean("hold-script-policy-1",gesturePolicy) else edit.remove("hold-script-policy-1")
                    check(edit.commit())
                    check(gesturePreferences.contains("hold-script-policy-1") == hadGesturePolicy &&
                        gesturePreferences.getBoolean("hold-script-policy-1", false) == gesturePolicy)
                }
            }
        }
    }
}
