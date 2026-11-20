package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.io.File
import org.json.JSONObject

/** More than display fixtures: actual local selected-pair models/readings and
 * native message accessibility actions. The authored source is never an output. */
class ImmersionTutorialDirectionsDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun spanishSourceToEnglishKeepsUsefulWordAndAccessibleOriginal() = exercise("es","en",false)
    @Test fun englishSourceToChineseCanChangeTheActualReadingScript() = exercise("en","zh",true)
    private fun exercise(source: String, target: String, script: Boolean) {
        MainActivityJourneyFixture("tutorial-$source-$target-real-local", { VipiModel(it) }).use { f ->
            val original = ImmersionTutorialSource.text(source)
            fun drawn(): String { var value="";f.instrumentation.runOnMainSync { value=f.paragraphs().singleOrNull()?.text?.toString().orEmpty() };return value }
            fun capture(name: String) {
                compose.waitForIdle();val settled=CountDownLatch(1)
                f.instrumentation.runOnMainSync { f.paragraphs().single().postOnAnimation { f.paragraphs().single().postOnAnimation { settled.countDown() } } }
                assertTrue(settled.await(3,TimeUnit.SECONDS));f.capture(name)
            }
            try {
                f.instrumentation.runOnMainSync {
                    f.model.selectKnown(source);f.model.selectTarget(target);f.model.selectImmersionMode(ImmersionMode.NEW_WORD);f.model.navigate(Screen.LANGUAGE)
                }
                f.launch();compose.onNodeWithText(f.base.getString(R.string.continue_action)).performClick()
                compose.waitUntil(180_000) { drawn().isNotBlank() && drawn()!=original }
                val shallow=drawn();capture("01-shallow-$source-$target")
                compose.onNodeWithTag("tutorial-mode-FULL_MESSAGES").performClick()
                compose.waitUntil(180_000) { drawn().isNotBlank() && drawn()!=original && drawn()!=shallow }
                val deep=drawn();capture("02-deep-$source-$target")
                // Invoke the genuine native screen-reader action by its public
                // localized label, rather than manufacturing held display state.
                f.instrumentation.runOnMainSync {
                    val view=f.paragraphs().single();val info=view.createAccessibilityNodeInfo()
                    val reveal=info.actionList.single { it.label?.toString()==f.base.getString(R.string.full_translation_meaning) }
                    assertTrue(view.performAccessibilityAction(reveal.id,null))
                }
                compose.waitUntil(5_000) { drawn()==original };capture("03-accessible-original-$source-$target")
                f.instrumentation.runOnMainSync {
                    val view=f.paragraphs().single();val action=view.createAccessibilityNodeInfo().actionList.single {
                        it.label?.toString()==f.base.getString(R.string.full_message_show_translation) }
                    assertTrue(view.performAccessibilityAction(action.id,null))
                }
                compose.waitUntil(5_000) { drawn()==deep }
                var nativeScript: String?=null
                if (script) {
                    compose.waitUntil(15_000) { compose.onAllNodesWithText(f.base.getString(R.string.tutorial_script)).fetchSemanticsNodes().isNotEmpty() }
                    compose.onNodeWithTag("tutorial-message").performTouchInput { doubleClick(center) }
                    compose.mainClock.advanceTimeBy(400);compose.waitForIdle()
                    compose.waitUntil(10_000) { drawn()!=deep && drawn().codePoints().anyMatch { Character.UnicodeScript.of(it)==Character.UnicodeScript.HAN } }
                    nativeScript=drawn();capture("04-native-script-$source-$target")
                    compose.onNodeWithTag("tutorial-message").performTouchInput { doubleClick(center) }
                    compose.mainClock.advanceTimeBy(400);compose.waitForIdle();compose.waitUntil(10_000) { drawn()==deep }
                }
                compose.onNodeWithText(f.base.getString(R.string.continue_action)).assertIsEnabled().performClick()
                compose.waitUntil { f.model.screen==Screen.ACCOUNT };assertNull(f.model.chat)
                File(f.output,"result.json").writeText(JSONObject().put("source_language",source).put("target_language",target)
                    .put("original",original).put("shallow",shallow).put("deep",deep).put("native_script",nativeScript?:JSONObject.NULL)
                    .put("native_accessibility_actions",true).put("actual_touch_script_switch",script).put("account_or_transport_created",false).toString(2))
            } catch (failure:Throwable) { runCatching{f.capture("failure")};throw failure }
        }
    }
}
