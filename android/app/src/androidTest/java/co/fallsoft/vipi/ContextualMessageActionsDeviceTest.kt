package co.fallsoft.vipi

import android.app.UiAutomation
import android.content.*
import android.os.*
import android.view.*
import android.view.accessibility.*
import android.view.inspector.WindowInspector
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.*
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import kotlinx.coroutines.*
import org.json.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

/** Actual ChatScreens candidate with isolated local history and no real relay. */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
class ContextualMessageActionsDeviceTest {
    @Test fun contextualActionsPreserveNativeMessageInteractions() {
        val ins = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiContextActionsRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val target = args.getString("vipiActionTarget") ?: "ja"; require(target in setOf("ja", "ar"))
        val targetName = if (target == "ja") "Japanese" else "Arabic"
        val targetWord = if (target == "ja") "ongaku" else "mūsīqā"
        val fullScript = if (target == "ja") "私は音楽が好きです。" else "أنا أحب الموسيقى."
        val fullReading = if (target == "ja") "Watashi wa ongaku ga suki desu." else "Anā uḥibb al-mūsīqā."
        val base = ins.targetContext; val config = Configurator.getInstance()
        val oldFlags = config.uiAutomationFlags; val oldIdle = config.waitForIdleTimeout
        config.uiAutomationFlags = UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES; config.waitForIdleTimeout = 0
        val automation = ins.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        val originalAutomationServiceFlags = automation.serviceInfo.flags
        automation.serviceInfo = automation.serviceInfo.apply { flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS }
        val device = UiDevice.getInstance(ins)
        fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command)).bufferedReader().use { it.readText().trim() }
        val settingKeys = listOf("enabled_accessibility_services", "accessibility_enabled", "touch_exploration_enabled")
        val before = settingKeys.associateWith { shell("settings get secure $it") }
        fun restore() { before.forEach { (key, value) ->
            if (value == "null") shell("settings delete secure $key") else {
                require(value.matches(Regex("[a-zA-Z0-9.$/:_\\-]+"))); shell("settings put secure $key $value")
            }
        } }
        val out = File(base.filesDir, "contextual-message-actions-$run"); check(!out.exists()); check(out.mkdirs())
        val root = File(base.cacheDir, "context-actions-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val incoming = UUID.randomUUID()
        val report = JSONObject().put("complete", false).put("production_chat", true).put("debug_candidate", true)
            .put("synthetic_history_and_transport", true).put("real_peer_traffic", false).put("target", target).put("font_scale", base.resources.configuration.fontScale)
        fun save() = File(out, "receipt.json").writeText(report.toString(2))
        fun await(name: String, seconds: Long = 20, condition: () -> Boolean) {
            val until = SystemClock.elapsedRealtime() + seconds * 1000
            while (SystemClock.elapsedRealtime() < until) { if (condition()) return; SystemClock.sleep(60) }
            error("Timed out: $name")
        }
        fun nodes(selector: BySelector): List<UiObject2> { automation.clearCache(); return device.findObjects(selector) }
        fun node(selector: BySelector): UiObject2 {
            var found: UiObject2? = null; await("control $selector") { found = nodes(selector).firstOrNull(); found != null }; return requireNotNull(found)
        }
        fun views(v: View): List<StableImmersionText> = when (v) {
            is StableImmersionText -> listOf(v)
            is ViewGroup -> (0 until v.childCount).flatMap { views(v.getChildAt(it)) }
            else -> emptyList()
        }
        fun paragraphs(): List<StableImmersionText> {
            var value = emptyList<StableImmersionText>(); ins.runOnMainSync { value = WindowInspector.getGlobalWindowViews().flatMap(::views) }; return value
        }
        fun music() = paragraphs().firstOrNull { it.visibleText().startsWith("I like ") }
        fun visible(v: StableImmersionText): String { var x = ""; ins.runOnMainSync { x = v.visibleText() }; return x }
        fun tree(n: AccessibilityNodeInfo): List<AccessibilityNodeInfo> = listOf(n) + (0 until n.childCount).flatMap { n.getChild(it)?.let(::tree) ?: emptyList() }
        fun nativeTree(): List<AccessibilityNodeInfo> { automation.clearCache(); return automation.rootInActiveWindow?.let(::tree).orEmpty() }
        fun nativeNode(predicate: (AccessibilityNodeInfo) -> Boolean): AccessibilityNodeInfo {
            var found: AccessibilityNodeInfo? = null
            await("native node in current window") { found = nativeTree().firstOrNull(predicate); found != null }
            return requireNotNull(found)
        }
        fun menuItem(label: String): UiObject2 {
            await("menu controls") { nativeTree().any { it.text?.toString() in setOf("Listen", "Stop listening", "Word switching", "Select text", "Copy original message") } }
            repeat(8) {
                nodes(By.text(label)).firstOrNull { it.visibleBounds.height() > 4 && it.visibleBounds.width() > 4 }?.let { return it }
                val scroll = nativeTree().firstOrNull { it.isScrollable && it.actionList.any { action -> action.id == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD } }
                check(scroll?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) == true) { "Menu action unreachable: $label" }
                SystemClock.sleep(250)
            }
            error("Menu action not found: $label")
        }
        fun menu(v: StableImmersionText) {
            await("settled focused native paragraph window") { var ready = false; ins.runOnMainSync { ready = v.isAttachedToWindow && v.hasWindowFocus() && v.isLaidOut && !v.isLayoutRequested && v.layout != null }; ready }
            var xy = IntArray(2); val probe = JSONObject()
            ins.runOnMainSync { v.getLocationOnScreen(xy); val l = requireNotNull(v.layout)
                xy[0] += ((l.getLineLeft(0) + l.getLineRight(0)) / 2).toInt()
                xy[1] += (l.getLineTop(0) + l.getLineBottom(0)) / 2
                probe.put("text", v.visibleText()).put("window_focus", v.hasWindowFocus()).put("focused", v.hasFocus())
                    .put("selectable", v.isTextSelectable).put("long_clickable", v.isLongClickable).put("selected", v.hasSelection())
                    .put("actions", JSONArray(v.createAccessibilityNodeInfo().actionList.map { it.toString() })) }
            val began = SystemClock.uptimeMillis(); val hold = ViewConfiguration.getLongPressTimeout().toLong() + 250
            probe.put("x", xy[0]).put("y", xy[1]).put("down_uptime_ms", began).put("hold_ms", hold)
            val probes = report.optJSONArray("menu_probes") ?: JSONArray().also { report.put("menu_probes", it) }; probes.put(probe); save()
            fun touch(action: Int) { MotionEvent.obtain(began, SystemClock.uptimeMillis(), action, xy[0].toFloat(), xy[1].toFloat(), 0).also {
                it.source = InputDevice.SOURCE_TOUCHSCREEN
                try { ins.sendPointerSync(it) } finally { it.recycle() }
            } }
            touch(MotionEvent.ACTION_DOWN)
            try { SystemClock.sleep(hold) } finally { touch(MotionEvent.ACTION_UP) }
            probe.put("up_uptime_ms", SystemClock.uptimeMillis()); save()
            await("contextual popup") { nativeTree().any { it.text?.toString() in setOf("Listen", "Stop listening", "Word switching", "Copy original message") } }
        }
        fun choose(v: StableImmersionText, label: String) { menu(v); menuItem(label).click() }
        fun screenshot(name: String) { check(device.takeScreenshot(File(out, "$name.png"))) }
        val clipboard = base.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        val previousClip = clipboard.primaryClip
        var reportRequests = 0
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                path == "/v1/me" -> ChatProfile(account, "actions_qa", "Actions QA").json()
                path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                path == "/v1/reports" -> { reportRequests++; error("This UI qualification must not submit a report") }
                else -> throw ServiceFailure(0, "offline")
            }
        }
        var chat: ChatSession? = null; var scenario: ActivityScenario<MainActivity>? = null
        save()
        try {
            MessageVault(context, account).use { vault -> vault.transaction {
                val now = System.currentTimeMillis()
                vault.put("incoming", incoming.toString(), StoredChat(ChatEnvelope(incoming, peer, account, now, 2, ByteArray(32)), "I need water.", "delivered").encode())
            } }
            runBlocking { withContext(Dispatchers.Main) { chat = ChatSession(context, transport, "actions-${UUID.randomUUID()}").also {
                it.start(); check(it.ready); it.find("alex"); it.send("I like music.", peer)
            } } }
            scenario = ActivityScenario.launch<MainActivity>(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
            scenario.onActivity { it.setContent { Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
                VipiTheme(if (target == "ar") Appearance.DARK else Appearance.LIGHT) { FriendConversationScreen(requireNotNull(chat), peer, "en", target, 1.0, qaContextualActions = true) {} }
            } } }
            node(By.res("message-input")); await("music paragraph") { music() != null }
            await("both catalog slots prepared") {
                paragraphs().map(::visible).let { "I like $targetWord." in it && it.any { value -> value.startsWith("I need ") && value != "I need water." } }
            }
            SystemClock.sleep(300)
            assertTrue(nodes(By.desc("Reading options")).isEmpty())
            val v = requireNotNull(music()); val phases = JSONArray(); var previous = ""; val until = SystemClock.elapsedRealtime() + 28_000
            while (SystemClock.elapsedRealtime() < until && phases.length() < 4) {
                val text = visible(v)
                if (text != previous) { val rect = android.graphics.Rect(); ins.runOnMainSync { v.getGlobalVisibleRect(rect) }
                    phases.put(JSONObject().put("text", text).put("bounds", rect.toShortString()).put("at", SystemClock.elapsedRealtime())); previous = text
                    report.put("automatic_phases", phases); save() }
                SystemClock.sleep(80)
            }
            assertTrue(phases.length() >= 4); assertEquals(1, (0 until phases.length()).map { phases.getJSONObject(it).getString("bounds") }.toSet().size)
            report.put("automatic_phases", phases); screenshot("resting"); save()
            // Real short tap at the current native source-word layout coordinates.
            val beforeTap = visible(v); var point = intArrayOf(0, 0)
            ins.runOnMainSync { val xy = IntArray(2); v.getLocationOnScreen(xy); val l = requireNotNull(v.layout)
                point = intArrayOf(xy[0] + ((l.getPrimaryHorizontal(7) + l.getPrimaryHorizontal(12)) / 2).toInt(), xy[1] + (l.getLineTop(0) + l.getLineBottom(0)) / 2) }
            device.click(point[0], point[1]); await("short tap changes word", 2) { visible(v) != beforeTap }
            report.put("short_word_tap", true)
            menu(v); screenshot("message-menu"); menuItem("Copy original message").click()
            var copied: String? = null; ins.runOnMainSync { copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString() }; assertEquals("I like music.", copied)
            report.put("copy_original_exact", true)
            choose(v, "Select text"); await("native selection") { var selected = false; ins.runOnMainSync { selected = v.hasSelection() }; selected }
            var selectedVisible = ""; ins.runOnMainSync { selectedVisible = v.visibleText(minOf(v.selectionStart, v.selectionEnd), maxOf(v.selectionStart, v.selectionEnd)) }
            assertEquals(visible(v), selectedVisible)
            val copyProbe = JSONObject().put("expected", selectedVisible)
            val clipboardEvents = JSONArray(); report.put("native_copy_probe", copyProbe.put("clipboard_events", clipboardEvents)); save()
            val clipListener = android.content.ClipboardManager.OnPrimaryClipChangedListener {
                clipboardEvents.put(JSONObject().put("uptime_ms", SystemClock.uptimeMillis())
                    .put("text", clipboard.primaryClip?.getItemAt(0)?.text?.toString())); save()
            }
            ins.runOnMainSync { clipboard.addPrimaryClipChangedListener(clipListener) }
            try {
                var stableKey = ""; var stableSince = 0L; var tapBounds = android.graphics.Rect()
                fun allViews(view: View): List<View> = listOf(view) + if (view is ViewGroup)
                    (0 until view.childCount).flatMap { allViews(view.getChildAt(it)) } else emptyList()
                await("settled app floating toolbar Copy control") {
                    val observed = JSONArray(); var bounds: android.graphics.Rect? = null
                    ins.runOnMainSync {
                        WindowInspector.getGlobalWindowViews().filter { it !== v.rootView }.forEach { rootView ->
                            allViews(rootView).filterIsInstance<android.widget.TextView>().filter { it.text?.toString() == "Copy" }.forEach { label ->
                                var clickable: View = label
                                while (!clickable.isClickable && clickable.parent is View) clickable = clickable.parent as View
                                val rect = android.graphics.Rect(); val shown = clickable.getGlobalVisibleRect(rect)
                                val rootRelative = android.graphics.Rect(rect); val rootOnScreen = IntArray(2)
                                rootView.getLocationOnScreen(rootOnScreen); rect.offset(rootOnScreen[0], rootOnScreen[1])
                                val title = (rootView.layoutParams as? WindowManager.LayoutParams)?.title?.toString().orEmpty()
                                val resource = runCatching { label.resources.getResourceName(label.id) }.getOrDefault("")
                                val ready = rootView.isAttachedToWindow && rootView.isShown && rootView.isLaidOut &&
                                    clickable.isAttachedToWindow && clickable.isShown && clickable.isLaidOut && !clickable.isLayoutRequested &&
                                    clickable.isEnabled && clickable.isClickable && shown && rect.width() > 8 && rect.height() > 8 &&
                                    (title.contains("PopupWindow") || resource.contains("floating_toolbar"))
                                observed.put(JSONObject().put("title", title).put("resource", resource).put("bounds", rect.toShortString())
                                    .put("root_relative_bounds", rootRelative.toShortString()).put("root_screen_x", rootOnScreen[0]).put("root_screen_y", rootOnScreen[1])
                                    .put("ready", ready).put("attached", clickable.isAttachedToWindow).put("shown", clickable.isShown).put("laid_out", clickable.isLaidOut))
                                if (ready) bounds = rect
                            }
                        }
                    }
                    copyProbe.put("window_controls", observed).put("observed_uptime_ms", SystemClock.uptimeMillis())
                    val rect = bounds
                    automation.clearCache()
                    val copyWindows = automation.windows
                    copyProbe.put("accessibility_windows", JSONArray(copyWindows.map { w ->
                        JSONObject().put("id", w.id).put("title", w.title?.toString()).put("type", w.type).put("active", w.isActive).put("focused", w.isFocused)
                    }))
                    val copyNodes = copyWindows.flatMap { w -> w.root?.let(::tree).orEmpty() }.filter { it.text?.toString() == "Copy" }
                    copyProbe.put("copy_accessibility_nodes", JSONArray(copyNodes.map { n ->
                        val b = android.graphics.Rect(); n.getBoundsInScreen(b)
                        JSONObject().put("window_id", n.windowId).put("package", n.packageName?.toString()).put("screen_bounds", b.toShortString()).put("visible", n.isVisibleToUser)
                    }))
                    val n = if (rect == null) null else copyNodes.firstOrNull { it.text?.toString() == "Copy" && it.isVisibleToUser && it.isEnabled &&
                        it.packageName?.toString() in setOf(base.packageName, "android") && android.graphics.Rect().also(it::getBoundsInScreen).let { b -> rect.contains(b.centerX(), b.centerY()) && b.width() > 8 && b.height() > 8 } }
                    val key = if (rect != null && n != null) "${n.windowId}:${n.packageName}:${rect.toShortString()}" else ""
                    val now = SystemClock.uptimeMillis()
                    if (key.isEmpty() || key != stableKey) { stableKey = key; stableSince = now }
                    if (n != null) copyProbe.put("accessibility_node", JSONObject().put("window_id", n.windowId).put("package", n.packageName?.toString()).put("resource", n.viewIdResourceName))
                    save()
                    (key.isNotEmpty() && now - stableSince >= 300).also { if (it) tapBounds = requireNotNull(rect) }
                }
                screenshot("native-selection-ready")
                copyProbe.put("tap_bounds", tapBounds.toShortString()).put("click_before_uptime_ms", SystemClock.uptimeMillis()); save()
                assertTrue(device.click(tapBounds.centerX(), tapBounds.centerY()))
                copyProbe.put("click_return_uptime_ms", SystemClock.uptimeMillis()); save()
                await("native Copy updates clipboard and ends selection") {
                    var selected = true
                    ins.runOnMainSync { copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString(); selected = v.hasSelection() }
                    copyProbe.put("clipboard_after", copied).put("selected_after", selected).put("completion_observed_uptime_ms", SystemClock.uptimeMillis()); save()
                    copied == selectedVisible && !selected && nodes(By.text("Copy")).isEmpty()
                }
                assertEquals(selectedVisible, copied)
            } finally { ins.runOnMainSync { clipboard.removePrimaryClipChangedListener(clipListener) } }
            report.put("native_selected_visible_copy", selectedVisible); save()
            await("selection ended") { var selected = true; ins.runOnMainSync { selected = v.hasSelection() }; !selected }
            // Focus through the native accessibility action, then a real keyboard key.
            val paragraph = nativeNode { it.contentDescription?.toString()?.startsWith("I like ") == true }
            assertTrue(paragraph.isFocused || paragraph.performAction(AccessibilityNodeInfo.ACTION_FOCUS))
            ins.sendKeyDownUpSync(KeyEvent.KEYCODE_MENU); menuItem("Select text"); device.pressBack()
            report.put("keyboard_menu_key", true)
            await("Menu Back dismisses popup and restores paragraph window") {
                var ready = false
                ins.runOnMainSync { ready = v.isAttachedToWindow && v.hasWindowFocus() && v.isLaidOut && !v.isLayoutRequested }
                ready && nodes(By.text("Select text")).isEmpty()
            }
            val focusAgain = nativeNode { it.contentDescription?.toString()?.startsWith("I like ") == true }
            assertTrue(focusAgain.isFocused || focusAgain.performAction(AccessibilityNodeInfo.ACTION_FOCUS))
            val keyTime = SystemClock.uptimeMillis()
            ins.sendKeySync(KeyEvent(keyTime, keyTime, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_F10, 0, KeyEvent.META_SHIFT_ON))
            ins.sendKeySync(KeyEvent(keyTime, SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, KeyEvent.KEYCODE_F10, 0, KeyEvent.META_SHIFT_ON))
            menuItem("Select text"); ins.sendKeyDownUpSync(KeyEvent.KEYCODE_ESCAPE)
            await("Escape dismisses contextual menu") { nodes(By.text("Select text")).isEmpty() }
            report.put("keyboard_shift_f10_and_escape", true)
            choose(v, targetName); await("full reading") { paragraphs().any { it.visibleText() == fullReading } }
            val full = paragraphs().first { it.visibleText() == fullReading }
            choose(full, "Show original script"); await("Japanese script") { paragraphs().any { it.visibleText() == fullScript } }
            val script = paragraphs().first { it.visibleText() == fullScript }
            menu(script); menuItem("Listen").click()
            var audioStarted = false
            await("actual native player", 15) { audioStarted = shell("dumpsys audio").lineSequence().any { "AudioPlaybackConfiguration" in it && "u/pid:${base.applicationInfo.uid}/" in it && "state:started" in it }; audioStarted }
            val speechNode = nativeNode { it.contentDescription?.toString() == fullScript }
            assertTrue(speechNode.performAction(speechNode.actionList.first { it.label?.toString() == "Message actions" && it.id != android.view.accessibility.AccessibilityNodeInfo.ACTION_LONG_CLICK }.id))
            menuItem("Stop listening").click(); report.put("native_audio_started_and_stop_reachable", audioStarted)
            choose(script, "Word switching"); await("music inline again") { music() != null }
            val water = paragraphs().first { it.visibleText().startsWith("I need ") }
            menu(water); menuItem("Report reply").click(); node(By.text("Report this message")); screenshot("incoming-report-confirmation"); device.pressBack()
            assertEquals(0, reportRequests); report.put("report_consent_reachable_no_submission", true); save()
            // Existing installed TalkBack, not merely a mocked manager flag.
            val service = "com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService"
            check(shell("pm path com.google.android.marvin.talkback").startsWith("package:"))
            val enabled = before.getValue("enabled_accessibility_services").takeUnless { it == "null" || it.isEmpty() }
            shell("settings put secure enabled_accessibility_services ${listOfNotNull(enabled, service).joinToString(":")}")
            shell("settings put secure accessibility_enabled 1")
            val manager = base.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
            await("TalkBack touch exploration") { manager.isTouchExplorationEnabled }
            scenario.onActivity { it.startActivity(Intent(it, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            await("native chat accessible") { nativeTree().any { it.contentDescription?.toString()?.startsWith("I like ") == true } }
            val p = nativeNode { it.contentDescription?.toString()?.startsWith("I like ") == true }
            assertTrue(p.isAccessibilityFocused || p.performAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS))
            // Actual TalkBack 15 service menu: documented down-then-right gesture.
            // Standard click on the service-owned menu entry invokes TalkBack's handler;
            // never call the application's custom action ID for this qualification.
            device.swipe(arrayOf(android.graphics.Point(200, 400), android.graphics.Point(200, 900), android.graphics.Point(700, 900)), 45)
            val actions = nativeNode { it.packageName?.toString() == "com.google.android.marvin.talkback" && it.text?.toString() == "Actions" }
            screenshot("talkback-service-menu")
            assertTrue(actions.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            val messageAction = nativeNode { it.packageName?.toString() == "com.google.android.marvin.talkback" && it.text?.toString() == "Message actions" }
            screenshot("talkback-service-actions")
            assertTrue(messageAction.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            menuItem("Copy original message"); screenshot("talkback-app-menu"); device.pressBack()
            report.put("talkback_service_menu_message_action", true)
            val w = nativeNode { n -> n.actionList.any { it.label?.toString() == "Switch music and $targetWord" } }
            val held = visible(requireNotNull(music())); assertTrue(w.performAction(w.actionList.first { it.label?.toString() == "Switch music and $targetWord" }.id))
            await("TalkBack manual word action") { visible(requireNotNull(music())) != held }
            val paused = visible(requireNotNull(music())); SystemClock.sleep(8500); assertEquals(paused, visible(requireNotNull(music())))
            report.put("service_active_direct_word_node_action", true).put("talkback_automatic_pause", true)
            restore(); report.put("settings_restored", true).put("complete", true); save()
        } catch (failure: Throwable) {
            report.put("failure_class", failure.javaClass.simpleName).put("failure_message", failure.message); save(); screenshot("failure"); throw failure
        } finally {
            restore(); scenario?.close(); chat?.let { runBlocking { withContext(Dispatchers.Main) { it.close() } } }
            ins.runOnMainSync { if (previousClip != null) clipboard.setPrimaryClip(previousClip) else clipboard.clearPrimaryClip() }
            root.deleteRecursively(); KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
            automation.serviceInfo = automation.serviceInfo.apply { flags = originalAutomationServiceFlags }
            config.uiAutomationFlags = oldFlags; config.waitForIdleTimeout = oldIdle
        }
    }
}
