package co.fallsoft.vipi

import android.view.WindowInsets
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/**
 * Actual Friend root, crypto/journal and incremental owner. The two recorded Spanish lexical
 * outputs isolate the palette/one-word visual; no SDK or supported-language certification and no
 * live person traffic.
 */
class GuavaConversationJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test
    fun shortOneWordConversationUsesNaturalNamesAndBothAppearances() {
        val sent = "Coffee tonight?"
        val reply = "Yes, 6:30 works!"
        val service =
            JourneyServices(
                profileRequired = false,
                accountDisplayName = "Alex",
                peerDisplayName = "Maya",
                expectedFriendPosts = 1,
                translationFactory = {
                    object : LanguageTranslation {
                        override suspend fun prepare(
                            source: String,
                            target: String,
                            cellularAllowed: Boolean,
                        ) = Unit

                        override suspend fun isReady(source: String, target: String) = true

                        override suspend fun translate(
                            text: String,
                            source: String,
                            target: String,
                        ): String =
                            when (text.lowercase(Locale.ROOT)) {
                                "coffee" -> "Café"
                                "yes" -> "Sí"
                                else ->
                                    text // identity is the real fallback contract, not another
                                         // introduced word
                            }

                        override fun close() = Unit
                    }
                },
            )
        MainActivityJourneyFixture("guava-short-friend", service::model).use { f ->
            try {
                f.instrumentation.runOnMainSync {
                    f.model.selectTarget("es")
                    f.model.selectImmersionMode(ImmersionMode.NEW_WORD)
                    f.model.changeAppearance(Appearance.LIGHT)
                }
                f.launch()
                compose.waitUntil(15_000) {
                    f.model.screen == Screen.HOME && f.model.chat?.ready == true
                }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNode(hasSetTextAction()).performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction()
                compose.waitUntil(15_000) { f.model.screen == Screen.CONVERSATION }
                f.bindConversationCapture(compose, "message-input")
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.onNodeWithTag("message-input").performTextInput(sent)
                compose.onNodeWithTag("message-send").performClick()
                compose.waitUntil(15_000) {
                    f.model.chat!!.messages(service.peer).any {
                        it.outgoing && it.text == sent && it.state in setOf("delivered", "read")
                    }
                }
                if (!PushDelivery.allowed(f.base))
                    compose.onNodeWithTag("reply-notification-later").performClick()
                val outgoing = f.model.chat!!.messages(service.peer).single { it.outgoing }.id
                compose.runOnIdle {
                    service.markOutgoingRead(outgoing)
                    service.queueAdditionalPeerReplyAndSignalInbox(reply)
                }
                compose.waitUntil(15_000) {
                    f.model.chat!!.messages(service.peer).size == 2 &&
                        f.model.chat!!.messages(service.peer).all {
                            f.model.chat!!.translations!!.state(it.id.toString(), it.text)?.phase ==
                                MessageTranslationPhase.READY
                        }
                }
                for (item in f.model.chat!!.messages(service.peer)) {
                    val value =
                        requireNotNull(
                            f.model.chat!!
                                .translations!!
                                .state(item.id.toString(), item.text)
                                ?.value
                        )
                    assertEquals(1, value.words!!.size)
                    assertEquals(
                        if (item.outgoing) "Café tonight?" else "Sí, 6:30 works!",
                        value.practiceText,
                    )
                }
                assertEquals(sent, service.peerReceived)
                fun ime(): Boolean {
                    var visible = false
                    f.instrumentation.runOnMainSync {
                        visible =
                            ActivityLifecycleMonitorRegistry.getInstance()
                                .getActivitiesInStage(Stage.RESUMED)
                                .single()
                                .window
                                .decorView
                                .rootWindowInsets
                                .isVisible(WindowInsets.Type.ime())
                    }
                    return visible
                }
                if (ime()) {
                    f.device.pressBack()
                    compose.waitUntil(5_000) { !ime() }
                }
                for ((appearance, name) in
                    listOf(
                        Appearance.LIGHT to "01-one-word-day",
                        Appearance.DARK to "02-one-word-night",
                    )) {
                    compose.runOnIdle { f.model.changeAppearance(appearance) }
                    compose.mainClock.advanceTimeBy(400)
                    compose.waitForIdle()
                    repeat(2) {
                        val latch = CountDownLatch(1)
                        f.instrumentation.runOnMainSync {
                            val root =
                                ActivityLifecycleMonitorRegistry.getInstance()
                                    .getActivitiesInStage(Stage.RESUMED)
                                    .single()
                                    .window
                                    .decorView
                            root.viewTreeObserver.registerFrameCommitCallback { latch.countDown() }
                            root.invalidate()
                        }
                        check(latch.await(3, TimeUnit.SECONDS))
                    }
                    f.capture(name)
                }
                service.assertNoPurchase()
            } catch (error: Throwable) {
                runCatching { f.capture("failure") }
                throw error
            } finally {
                f.stopActivity()
                service.close()
            }
        }
    }
}
