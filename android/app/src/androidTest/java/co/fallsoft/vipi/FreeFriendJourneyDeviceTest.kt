package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/**
 * Actual free profile/root/send route with controlled relay and word output. Not translation,
 * reading, speech or language-support certification.
 */
class FreeFriendJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test
    fun profileAndFriendSendNeedNoCommerceAndKeepAuthoredOriginal() {
        val services =
            JourneyServices(
                profileRequired = true,
                translationFactory = {
                    object : LanguageTranslation {
                        override suspend fun prepare(
                            source: String,
                            target: String,
                            cellularAllowed: Boolean,
                        ) = Unit

                        override suspend fun translate(
                            text: String,
                            source: String,
                            target: String,
                        ) = "hola"

                        override fun close() = Unit
                    }
                },
            )
        MainActivityJourneyFixture("free-friend-word-growth", services::model).use { f ->
            fun screen(value: Screen) = compose.waitUntil(15_000) { f.model.screen == value }
            try {
                f.launch()
                screen(Screen.PROFILE)
                compose
                    .onNodeWithTag("profile-name")
                    .performScrollTo()
                    .performTextInput("Journey Tester")
                compose
                    .onNodeWithTag("profile-username")
                    .performScrollTo()
                    .performTextInput("journey_tester")
                compose
                    .onNodeWithTag("profile-submit")
                    .performScrollTo()
                    .assertIsEnabled()
                    .performClick()
                screen(Screen.HOME)
                compose
                    .onNodeWithText(f.base.getString(R.string.ui_f173182378d0))
                    .assertDoesNotExist()
                compose
                    .onNodeWithContentDescription(f.base.getString(R.string.nav_settings))
                    .performClick()
                screen(Screen.SETTINGS)
                compose.onNodeWithText(f.base.getString(R.string.nav_plan)).assertDoesNotExist()
                fun imeVisible(): Boolean {
                    var visible = false
                    f.instrumentation.runOnMainSync {
                        visible =
                            android.view.inspector.WindowInspector.getGlobalWindowViews().any { view
                                ->
                                view.rootWindowInsets?.let {
                                    androidx.core.view.WindowInsetsCompat.toWindowInsetsCompat(it)
                                        .isVisible(androidx.core.view.WindowInsetsCompat.Type.ime())
                                } == true
                            }
                    }
                    return visible
                }
                f.capture("settings-before-system-back")
                if (imeVisible()) {
                    f.device.pressBack()
                    compose.waitUntil(8_000) { !imeVisible() }
                }
                assertFalse(
                    "System Back navigation starts with an actually hidden IME",
                    imeVisible(),
                )
                f.capture("settings-hidden-ime-before-system-back")
                f.device.pressBack()
                screen(Screen.HOME)
                compose
                    .onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat))
                    .performClick()
                screen(Screen.NEW_CHAT)
                compose
                    .onNode(hasSetTextAction())
                    .performScrollTo()
                    .performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction()
                screen(Screen.CONVERSATION)
                val exact = "Hello, friend!"
                compose.onNodeWithTag("message-input").performTextInput(exact)
                compose.onNodeWithTag("message-send").assertIsEnabled().performClick()
                compose.waitUntil(15_000) { services.friendPosts.get() == 1 }
                val chat = requireNotNull(f.model.chat)
                compose.waitUntil(15_000) { chat.messages(services.peer).any { it.text == exact } }
                val row = chat.messages(services.peer).single { it.text == exact }
                val owner = requireNotNull(chat.translations)
                compose.waitUntil(15_000) {
                    owner.state(row.id.toString(), exact)?.phase == MessageTranslationPhase.READY
                }
                val value = requireNotNull(owner.state(row.id.toString(), exact)?.value)
                assertEquals(exact, value.original)
                assertEquals(exact, value.meaningText)
                assertEquals(1, value.words!!.size)
                assertTrue(value.words.single().source in listOf("Hello", "friend"))
                assertEquals(exact, services.peerReceived)
                services.assertNoPurchase()
                f.capture("free-friend-original-and-one-practice-word")
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }
                throw failure
            } finally {
                f.stopActivity()
                services.close()
            }
        }
    }
}
