package co.fallsoft.vipi

import android.app.UiAutomation
import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.Intent
import android.os.ParcelFileDescriptor
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityManager
import android.view.accessibility.AccessibilityNodeInfo
import android.view.inspector.WindowInspector
import androidx.activity.ComponentActivity
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.Configurator
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionSpan

/** Actual service qualification on the dedicated emulator, restoring settings. */
class TalkBackImmersionDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    @Test fun actualTalkBackPausesAlternationAndExposesManualWordAction() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val run = InstrumentationRegistry.getArguments().getString("vipiTalkBackRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val context = instrumentation.targetContext
        val config = Configurator.getInstance(); val oldFlags = config.uiAutomationFlags
        config.uiAutomationFlags = UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES
        val automation = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        fun shell(command: String): String = ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command))
            .bufferedReader().use { it.readText().trim() }
        fun restore(key: String, value: String) {
            if (value == "null") shell("settings delete secure $key")
            else { check(value.matches(Regex("[a-zA-Z0-9.$/:_\\-]+"))); shell("settings put secure $key $value") }
        }
        val keys = listOf("enabled_accessibility_services", "accessibility_enabled", "touch_exploration_enabled")
        val before = keys.associateWith { shell("settings get secure $it") }
        val service = "com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService"
        val manager = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        var ownerRef: ConversationImmersion? = null
        val visible = mutableStateOf(true)
        val longMessage = mutableStateOf(false)
        // Renderer/accessibility stress fixture, not a translation acceptance case.
        val longSource = List(32) { "music" }.plus("tea").joinToString(" ")
        val longTarget = List(32) { "muziki" }.plus("chai").joinToString(" ")
        val longResult = ImmersionResult(longSource, longTarget, (0..32).map { index ->
            ImmersionSpan(index * 6, index * 6 + if (index == 32) 3 else 5,
                if (index == 32) "tea" else "music", if (index == 32) "chai" else "muziki",
                index * 7, index * 7 + if (index == 32) 4 else 6)
        })
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun reading(): String? {
            var value: String? = null
            instrumentation.runOnMainSync { value = WindowInspector.getGlobalWindowViews().flatMap { paragraphs(it) }.firstOrNull()?.visibleText() }
            return value
        }
        fun nodes(root: AccessibilityNodeInfo): List<AccessibilityNodeInfo> = listOf(root) + (0 until root.childCount).flatMap { index -> root.getChild(index)?.let(::nodes) ?: emptyList() }
        try {
            check(shell("pm path com.google.android.marvin.talkback").startsWith("package:"))
            compose.setContent {
                if (visible.value) VipiTheme(Appearance.LIGHT) {
                    val scope = rememberCoroutineScope()
                    val owner = remember { ConversationImmersion(context, "en", "sw", .75, qaModelsReady = true).also { ownerRef = it; it.selectInputLanguage("talkback-qa", "en") } }
                    val speech = remember { SpeechPlayback(context, "en", "sw", scope) }
                    DisposableEffect(Unit) { onDispose { owner.close(); speech.close() } }
                    Box(Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp)) {
                        if (longMessage.value) ImmersionBubble(longResult, ReadingMode.IMMERSED, source = "en", target = "sw")
                        else ConversationImmersionText("I like music.", "talkback-qa", owner, speech, false, {}, metadata = { Text("A message") })
                    }
                }
            }
            try { compose.waitUntil(20_000) { reading() == "I like muziki." } }
            finally {
                val diagnostic = JSONObject().put("actualVisibleText", reading() ?: JSONObject.NULL).put("expectedVisibleText", "I like muziki.")
                instrumentation.runOnMainSync {
                    val owner = ownerRef
                    val outcome = owner?.lastOutcome
                    val invocation = owner?.lastInvocation
                    diagnostic.put("ownerReady", owner?.ready ?: JSONObject.NULL)
                        .put("status", outcome?.status?.name ?: JSONObject.NULL)
                        .put("origin", outcome?.origin?.name ?: JSONObject.NULL)
                        .put("fallbackStatus", outcome?.fallbackStatus?.name ?: JSONObject.NULL)
                        .put("localCalls", outcome?.localTranslationCalls ?: JSONObject.NULL)
                        .put("sourceRecognitionCalls", invocation?.sourceRecognition ?: JSONObject.NULL)
                        .put("partialCalls", invocation?.partialPresentation ?: JSONObject.NULL)
                        .put("renderedSpans", JSONArray(outcome?.result?.spans?.map { JSONObject().put("original", it.original).put("target", it.translated) } ?: emptyList<JSONObject>()))
                        .put("viewRoots", JSONArray(WindowInspector.getGlobalWindowViews().flatMap { paragraphs(it) }.map { JSONObject().put("shown", it.isShown).put("text", it.visibleText()) }))
                }
                File(context.filesDir, "talkback-precondition-$run.json").writeText(diagnostic.toString(2))
            }
            val enabled = before.getValue("enabled_accessibility_services").takeUnless { it == "null" || it.isEmpty() }
            val services = listOfNotNull(enabled, service).joinToString(":")
            check(services.matches(Regex("[a-zA-Z0-9.$/:_\\-]+")))
            // UiAutomation splits arguments itself; quotes would become literal
            // characters in the component name rather than shell syntax.
            shell("settings put secure enabled_accessibility_services $services")
            shell("settings put secure accessibility_enabled 1")
            compose.waitUntil(20_000) { manager.isTouchExplorationEnabled }
            // TalkBack may open its first-use tutorial. Return to the already
            // running test activity without editing TalkBack's own preferences.
            compose.runOnIdle { compose.activity.startActivity(Intent(compose.activity, ComponentActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            compose.waitUntil(10_000) { automation.rootInActiveWindow?.packageName?.toString() == context.packageName }
            val held = requireNotNull(reading())
            val until = android.os.SystemClock.uptimeMillis() + 8_000
            while (android.os.SystemClock.uptimeMillis() < until) {
                assertTrue(manager.isTouchExplorationEnabled); assertEquals(held, reading())
                android.os.SystemClock.sleep(100)
            }
            // The service's delayed notification permission prompt can appear
            // after its tutorial. Dismiss with Back (no permission decision),
            // then inspect the app's actual accessible window, never that dialog.
            val prompt = automation.rootInActiveWindow?.let(::nodes).orEmpty()
            if (prompt.any { it.text?.toString() == "Allow Android Accessibility Suite to send you notifications?" }) {
                assertTrue(automation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            }
            compose.runOnIdle { compose.activity.startActivity(Intent(compose.activity, ComponentActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            compose.waitUntil(10_000) { automation.rootInActiveWindow?.packageName?.toString() == context.packageName }
            var tree = nodes(requireNotNull(automation.rootInActiveWindow))
            val snapshot = JSONArray(tree.map { node -> JSONObject()
                .put("class", node.className).put("text", node.text).put("description", node.contentDescription)
                .put("visible", node.isVisibleToUser).put("actions", JSONArray(node.actionList.map { it.toString() })) })
            val treeFile = File(context.filesDir, "talkback-tree-$run.json"); check(!treeFile.exists())
            treeFile.writeText(snapshot.toString(2))
            var menu: AccessibilityNodeInfo? = requireNotNull(tree.firstOrNull { it.contentDescription?.toString() == "Reading options" })
            while (menu != null && menu.actionList.none { it.id == AccessibilityNodeInfo.ACTION_CLICK }) menu = menu.parent
            assertTrue(requireNotNull(menu).performAction(AccessibilityNodeInfo.ACTION_CLICK))
            try {
                compose.waitUntil(5_000) {
                    automation.rootInActiveWindow?.let(::nodes).orEmpty().any { it.text?.toString() == "Full translation" }
                }
            } finally {
                val observed = automation.rootInActiveWindow?.let(::nodes).orEmpty()
                File(context.filesDir, "talkback-menu-$run.json").writeText(JSONArray(observed.map { JSONObject().put("text", it.text ?: JSONObject.NULL).put("description", it.contentDescription ?: JSONObject.NULL).put("visible", it.isVisibleToUser) }).toString(2))
                androidx.test.uiautomator.UiDevice.getInstance(instrumentation).takeScreenshot(File(context.filesDir, "talkback-menu-$run.png"))
            }
            val menuLabels = nodes(requireNotNull(automation.rootInActiveWindow)).map { it.text?.toString() }
            for (inactive in listOf("Pause word switching", "Resume word switching", "Word switching speed")) {
                assertFalse("Inactive automatic controls must be absent with TalkBack", inactive in menuLabels)
            }
            assertTrue("Show original words now" in menuLabels)
            assertTrue(automation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            compose.waitForIdle()
            tree = nodes(requireNotNull(automation.rootInActiveWindow))
            val paragraph = requireNotNull(tree.firstOrNull { it.contentDescription?.toString() == held }) { "Visible paragraph missing from native accessibility tree: $held" }
            assertTrue(paragraph.isVisibleToUser)
            assertFalse(held.contains('\uFFFC'))
            val actionNode = requireNotNull(tree.firstOrNull { node -> node.actionList.any { it.label?.toString() == "Switch music and muziki" } }) { "Word action missing from native accessibility tree" }
            val action = actionNode.actionList.first { it.label?.toString() == "Switch music and muziki" }
            assertTrue(actionNode.performAction(action.id))
            compose.waitUntil(5_000) { reading() != held }
            val switched = requireNotNull(reading())
            assertTrue(switched in listOf("I like music.", "I like muziki."))
            compose.runOnIdle { longMessage.value = true }
            compose.waitUntil(5_000) { reading()?.endsWith(" chai") == true }
            val longTree = nodes(requireNotNull(automation.rootInActiveWindow))
            val chooser = longTree.first { node -> node.actionList.any { it.label?.toString() == "Choose a word to switch" } }
            assertEquals(32, chooser.actionList.count { it.label != null })
            assertTrue(chooser.performAction(chooser.actionList.first { it.label?.toString() == "Choose a word to switch" }.id))
            compose.waitUntil(5_000) {
                automation.rootInActiveWindow?.let(::nodes).orEmpty().any { it.text?.toString() == "Switch a word" }
            }
            compose.waitForIdle()
            var chosen = false
            for (page in 0..12) {
                android.os.SystemClock.sleep(250)
                val dialog = nodes(requireNotNull(automation.rootInActiveWindow))
                val item = dialog.firstOrNull { it.text?.toString() == "tea · chai" }
                if (item != null) {
                    var button: AccessibilityNodeInfo? = item
                    while (button != null && button.actionList.none { it.id == AccessibilityNodeInfo.ACTION_CLICK }) button = button.parent
                    assertTrue(requireNotNull(button).performAction(AccessibilityNodeInfo.ACTION_CLICK)); chosen = true; break
                }
                val scroll = requireNotNull(dialog.firstOrNull { node -> node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD } }) {
                    dialog.joinToString("\n") { "${it.className}: ${it.text} ${it.actionList}" }
                }
                assertTrue(scroll.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))
                // Native actions schedule Compose scrolling; advance its test
                // clock and wait for layout before requesting the next page.
                compose.waitForIdle()
            }
            assertTrue("The 33rd word is reachable through native accessibility scrolling", chosen)
            compose.waitUntil(5_000) { reading()?.endsWith(" tea") == true }
            val resumeFrom = requireNotNull(reading())
            keys.forEach { restore(it, before.getValue(it)) }
            if (before.getValue("touch_exploration_enabled") != "1") {
                compose.waitUntil(10_000) { !manager.isTouchExplorationEnabled }
                compose.waitUntil(12_000) { reading() != resumeFrom }
                assertTrue(nodes(requireNotNull(automation.rootInActiveWindow)).any {
                    it.contentDescription?.toString() == "Pause word switching"
                })
            }
            val report = File(context.filesDir, "talkback-immersion-$run.json"); check(!report.exists())
            report.writeText(JSONObject().put("actual_service", service).put("touch_exploration_verified", true)
                .put("eight_second_pause", true).put("accessible_visible_text", true).put("native_custom_action", true)
                .put("thirty_third_word_native_chooser", true)
                .put("inactive_automatic_controls_hidden", true).put("automatic_controls_restored", true)
                .put("settings_restored", true).put("speech_listening_acceptance", false).toString(2))
        } finally {
            keys.forEach { restore(it, before.getValue(it)) }
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            config.uiAutomationFlags = oldFlags
        }
    }
}
