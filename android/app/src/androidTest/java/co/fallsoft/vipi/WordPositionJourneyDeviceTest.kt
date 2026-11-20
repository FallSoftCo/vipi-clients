package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID

/** Native fresh conversations with real journal/crypto and controlled lexical
 * equivalents ONLY to isolate selection. No SDK translation or TTS certification. */
class WordPositionJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun headerSwitchKeepsDraftAndNativeIncomingWordsAppearAtInitialMiddleAndFinalPositions() {
        val cases = listOf(Triple("00000000-0000-4000-8000-000000000002", "Coffee", "café after work?"),
            Triple("00000000-0000-4000-8000-00000000000b", "after", "Coffee después work?"),
            Triple("00000000-0000-4000-8000-000000000001", "work", "Coffee after trabajo?"))
        cases.forEachIndexed { index, (rawID, selected, expected) ->
            val services = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya", translationFactory = {
                object : LanguageTranslation {
                    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                    override suspend fun translate(text: String, source: String, target: String) = when(text.lowercase()) {
                        "hello" -> "hola"; "coffee" -> "café"; "after" -> "después"; "work" -> "trabajo"
                        "coffee after work?" -> "¿Café después del trabajo?"; else -> error("Unexpected controlled input")
                    }
                    override fun close() = Unit
                }
            })
            MainActivityJourneyFixture("word-position-$index", services::model).use { f ->
                fun screen(value: Screen) = compose.waitUntil(15_000) { f.model.screen == value }
                try {
                    f.launch(); screen(Screen.HOME)
                    compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performClick(); screen(Screen.NEW_CHAT)
                    compose.onNode(hasSetTextAction()).performScrollTo().performTextInput("journey_friend")
                    compose.onNode(hasSetTextAction()).performImeAction(); screen(Screen.CONVERSATION)
                    compose.onNodeWithTag("message-input").performTextInput("Hello")
                    compose.onNodeWithTag("message-send").performClick()
                    val chat = requireNotNull(f.model.chat)
                    compose.waitUntil(15_000) { chat.messages(services.peer).any { it.outgoing && it.state == "delivered" } }
                    val draft = "Shall we meet at six? ☕"
                    compose.onNodeWithTag("message-input").performTextInput(draft)
                    val caret = compose.onNodeWithTag("message-input").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.TextSelectionRange]
                    compose.onNodeWithTag("conversation-immersion").performTouchInput { click() }
                    compose.waitUntil(8_000) { f.model.immersionMode == ImmersionMode.NEW_WORD && chat.translations?.mode == ImmersionMode.NEW_WORD }
                    assertEquals(draft, chat.compose(services.peer)); compose.onNodeWithTag("message-input").assertTextEquals(draft)
                    assertEquals(caret, compose.onNodeWithTag("message-input").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.TextSelectionRange])
                    val id = UUID.fromString(rawID); val original = "Coffee after work?"
                    compose.runOnIdle { services.queueAdditionalPeerReplyAndSignalInbox(original, id) }
                    compose.waitUntil(15_000) { chat.translations?.state(rawID, original)?.phase == MessageTranslationPhase.READY }
                    val value = requireNotNull(chat.translations?.state(rawID, original)?.value)
                    assertEquals(listOf(selected), value.words!!.map { it.source }); assertEquals(expected, value.practiceText)
                    assertTrue("Actual native paragraph must paint the selected lexical position", f.device.wait(Until.hasObject(By.text(expected)), 8_000))
                    compose.waitForIdle(); f.device.waitForIdle(); f.capture("0${index+1}-native-word-position")
                    assertEquals(original, chat.messages(services.peer).single { it.id == id }.text)
                    assertEquals(draft, chat.compose(services.peer)); assertEquals(1, services.deviceRegistrations.get()); services.assertNoPurchase()
                } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
                finally { f.stopActivity(); services.close() }
            }
        }
    }
}
