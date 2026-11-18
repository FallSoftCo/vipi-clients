package co.fallsoft.vipi

import android.app.Application
import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModelStore
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import kotlinx.coroutines.*
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/** Full production screen/session/vault success path. All service requests are
 * local fakes; no auth, provider, purchase, real device enrollment or message send. */
class BotConversationSendDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun nativeDraftConsentAndSendPersistOneConfirmedReplyWithCurrentDevice() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val base = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val run = InstrumentationRegistry.getArguments().getString("vipiBotSendRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "bot-send-fullscreen-$run")
        check(!output.exists()) { "Use a new vipiBotSendRun to preserve earlier evidence" }
        check(output.mkdirs())
        val prefix = "bot-send-${UUID.randomUUID()}-"
        val root = File(base.cacheDir, prefix).apply { check(mkdirs()) }
        val preferences = mutableSetOf<String>()
        val application = object : Application() {
            init { attachBaseContext(base) }
            override fun getApplicationContext(): Context = this
            override fun getNoBackupFilesDir(): File = File(root, "private").apply { mkdirs() }
            override fun getFilesDir(): File = File(root, "files").apply { mkdirs() }
            override fun getCacheDir(): File = File(root, "cache").apply { mkdirs() }
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                preferences += prefix + name
                return base.getSharedPreferences(prefix + name, mode)
            }
        }
        val account = UUID.randomUUID()
        val prompt = "A synthetic greeting for this local test."
        val reply = "Synthetic reply received."
        val privateFriend = "PRIVATE_FRIEND_CONTENT_MUST_NOT_LEAVE_VAULT"
        val posts = AtomicInteger(0)
        val remaining = AtomicInteger(150)
        var requestID: String? = null
        lateinit var registeredDevice: DeviceCredential
        fun allowance() = JSONObject().put("available", true).put("service_ready", true)
            .put("remaining_replies", remaining.get()).put("monthly_replies", 150)
            .put("period", "2098-12").put("resets_at", "2099-01-01T00:00:00Z").put("max_context_bytes", 8192)
        fun entitlements(): JSONObject {
            fun plan() = JSONObject().put("active", true).put("expires_at", JSONObject.NULL)
                .put("trial_ends_at", JSONObject.NULL).put("review_access", true).put("access_source", "review_complimentary")
            return JSONObject().put("base", plan()).put("bot_mini", plan().put("available", true))
                .put("billing_account_id", "b".repeat(64)).put("server_time", Instant.now().toString())
        }
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                method == "GET" && path == "/v1/entitlements" -> entitlements()
                method == "GET" && path == "/v1/bot/allowance" -> allowance()
                method == "POST" && path == "/v1/bot/messages" -> {
                    check(posts.incrementAndGet() == 1) { "The screen must dispatch only one request" }
                    // Boolean assertion avoids including the synthetic credential in a failure log.
                    check(device == registeredDevice) { "Send must attach the retained registered device" }
                    val sent = requireNotNull(body)
                    check(sent.length() == 3 && sent.getString("consent_version") == "deepseek-v1")
                    val context = sent.getJSONArray("messages")
                    check(context.length() == 1)
                    check(context.getJSONObject(0).getString("role") == "user")
                    check(context.getJSONObject(0).getString("content") == prompt)
                    check(!sent.toString().contains(privateFriend))
                    val id = sent.getString("request_id")
                    UUID.fromString(id)
                    requestID = id
                    remaining.decrementAndGet()
                    JSONObject().put("request_id", id).put("reply", reply).put("allowance", allowance())
                }
                else -> error("Unexpected service request in isolated screen test: $method $path")
            }
        }
        val noTranslation = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model preparation")
            override suspend fun translate(text: String, source: String, target: String): String = error("No model inference")
            override fun close() = Unit
        }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val models = ViewModelStore()
        val visible = mutableStateOf(true)
        lateinit var model: VipiModel
        lateinit var bot: BotSession
        var initialized = false
        var host: ComponentActivity? = null
        var originalSoftInputMode: Int? = null
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun fullyVisible(view: View): Boolean {
            val visibleBounds = Rect()
            return view.isShown && view.width > 0 && view.height > 0 && view.getLocalVisibleRect(visibleBounds) &&
                visibleBounds.left <= 0 && visibleBounds.top <= 0 &&
                visibleBounds.right >= view.width && visibleBounds.bottom >= view.height
        }
        fun replyVisibleInNativeScreen(): Boolean {
            var displayed: String? = null
            instrumentation.runOnMainSync {
                host?.window?.decorView?.let { rootView ->
                    paragraphs(rootView).firstOrNull { it.displayedOriginal == reply && fullyVisible(it) }?.let {
                        val actual = it.visibleText()
                        if (actual.isNotBlank() && it.contentDescription?.toString() == actual) displayed = actual
                    }
                }
            }
            val text = displayed ?: return false
            // Native TextView supplies a projected content description for spans.
            // Require that the same actually drawn text is exposed on screen.
            val node = device.findObject(By.desc(text)) ?: device.findObject(By.text(text)) ?: return false
            return !node.visibleBounds.isEmpty
        }
        fun imeVisible(): Boolean {
            var shown = false
            instrumentation.runOnMainSync {
                shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                    view.rootWindowInsets?.let {
                        WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime())
                    } == true
                }
            }
            return shown
        }
        fun capture(name: String) {
            compose.waitForIdle()
            check(device.takeScreenshot(File(output, "$name.png")))
            device.dumpWindowHierarchy(File(output, "$name.xml"))
            val snapshot = JSONObject()
            instrumentation.runOnMainSync {
                snapshot.put("host_class", host?.javaClass?.name)
                    .put("original_soft_input_mode", originalSoftInputMode)
                    .put("current_soft_input_mode", host?.window?.attributes?.softInputMode)
                val nodes = JSONArray()
                host?.window?.decorView?.let { rootView -> paragraphs(rootView).forEach { view ->
                    val bounds = Rect(); view.getGlobalVisibleRect(bounds)
                    nodes.put(JSONObject().put("original", view.displayedOriginal)
                        .put("drawn_text", view.visibleText()).put("view_text", view.text.toString())
                        .put("content_description", view.contentDescription?.toString())
                        .put("fully_visible", fullyVisible(view)).put("shown", view.isShown)
                        .put("global_visible_bounds", bounds.toShortString()))
                } }
                snapshot.put("native_paragraphs", nodes)
            }
            File(output, "$name-native.json").writeText(snapshot.toString(2))
        }
        try {
            instrumentation.runOnMainSync {
                // createComposeRule launches the manifest's generic test activity,
                // which otherwise need not inherit MainActivity's adjustResize.
                host = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                    .filterIsInstance<ComponentActivity>().single { it.javaClass == ComponentActivity::class.java }
                requireNotNull(host).apply {
                    originalSoftInputMode = window.attributes.softInputMode
                    window.setSoftInputMode((window.attributes.softInputMode and
                        WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST.inv()) or WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
                    enableEdgeToEdge()
                }
                MessageVault(application, account).use { vault ->
                    registeredDevice = DeviceCredential.load(vault)
                    vault.transaction {
                        vault.put("local", "registered-device", registeredDevice.id.toString().toByteArray())
                        vault.put("message", "friend-private", privateFriend.toByteArray())
                    }
                }
                model = VipiModel(application, noTranslation)
                models.put("isolated-bot-send", model)
                val plans = Subscriptions(application, transport, scope)
                val field = VipiModel::class.java.getDeclaredField("subscriptions\$delegate").apply { isAccessible = true }
                @Suppress("UNCHECKED_CAST")
                (field.get(model) as MutableState<Any?>).value = plans
                bot = BotSession(application, account, transport)
                val botField = VipiModel::class.java.getDeclaredField("bot\$delegate").apply { isAccessible = true }
                @Suppress("UNCHECKED_CAST")
                (botField.get(model) as MutableState<Any?>).value = bot
                initialized = true
                check(!bot.consent && bot.draft.isEmpty() && bot.messages.isEmpty())
                check(model.knownLanguage == "en" && model.targetLanguage == "es")
            }
            compose.setContent { if (visible.value) VipiTheme(Appearance.LIGHT) { BotConversationScreen(model, bot) } }
            compose.waitUntil(10_000) { model.subscriptions?.accessCheckState == AccessCheckState.LOADED && bot.allowance != null }
            compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
            compose.waitUntil(8_000) { imeVisible() }
            compose.onNodeWithTag("bot-message-input").assertIsFocused().performTextInput(prompt)
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
            compose.runOnIdle { assertFalse(bot.consent); assertEquals(prompt, bot.draft); assertEquals(0, posts.get()) }
            compose.onNodeWithText(base.getString(R.string.ui_f173182378d0)).assertIsDisplayed()
            capture("01-local-draft-keyboard-before-consent")

            compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
            compose.runOnIdle { assertFalse(bot.consent); assertEquals(0, posts.get()) }
            compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
            compose.waitUntil(5_000) { bot.consent }
            compose.onNodeWithTag("bot-message-input").assertTextEquals(prompt)
            compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
            compose.waitUntil(10_000) { !bot.busy && bot.messages.size == 2 }
            compose.runOnIdle {
                assertEquals(1, posts.get())
                assertEquals("", bot.draft)
                assertEquals(listOf("user", "assistant"), bot.messages.map { it.role })
                assertEquals(listOf("confirmed", "confirmed"), bot.messages.map { it.status })
                assertEquals(listOf(prompt, reply), bot.messages.map { it.text })
                assertTrue(bot.messages.all { it.requestID == requestID })
                assertEquals(149, bot.allowance?.remaining)
                assertNull(bot.notice)
            }
            // Capture the actual layout before asserting, including a mismatch.
            capture("02-before-reply-visibility-assertion")
            // This requires a reply-bound native view fully within the viewport
            // AND its drawn projection in accessibility, not only session data.
            compose.waitUntil(8_000) { replyVisibleInNativeScreen() }
            assertTrue("Returned reply must be fully visible in the real screen", replyVisibleInNativeScreen())
            compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
            compose.waitUntil(8_000) { imeVisible() }
            capture("03-confirmed-reply-keyboard")

            MessageVault(application, account).use { vault ->
                vault.transaction {
                    assertNull(vault.get("bot-settings", "draft"))
                    assertEquals("deepseek-v1", vault.get("bot-settings", "consent")?.toString(Charsets.UTF_8))
                    assertEquals(privateFriend, vault.get("message", "friend-private")?.toString(Charsets.UTF_8))
                }
                assertTrue(DeviceCredential.registered(vault) == registeredDevice)
            }
            // Reopen the actual encrypted session to establish durable success
            // and ensure merely reopening history cannot dispatch another POST.
            BotSession(application, account, transport).use { restored ->
                assertTrue(restored.consent)
                assertEquals("", restored.draft)
                assertEquals(listOf(prompt, reply), restored.messages.map { it.text })
                assertTrue(restored.messages.all { it.status == "confirmed" && it.requestID == requestID })
            }
            assertEquals(1, posts.get())
            File(output, "result.json").writeText(JSONObject().put("pass", true).put("posts", posts.get())
                .put("registered_device_attached", true).put("friend_content_excluded", true)
                .put("confirmed_messages", 2).put("remaining_replies", 149).put("durable_reopen", true)
                .put("native_ime_before_consent", true).put("reply_fully_visible_with_accessibility_projection", true)
                .put("test_host_adjust_resize", true).put("network", "fake ChatTransport only").toString(2))
        } catch (failure: Throwable) {
            runCatching { capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
            throw failure
        } finally {
            if (initialized) {
                compose.runOnIdle { visible.value = false }
                compose.waitForIdle()
                instrumentation.runOnMainSync {
                    models.clear(); scope.cancel()
                    originalSoftInputMode?.let { mode -> host?.window?.setSoftInputMode(mode) }
                    android.view.inspector.WindowInspector.getGlobalWindowViews().forEach {
                        it.windowInsetsController?.hide(android.view.WindowInsets.Type.ime())
                    }
                }
            } else { instrumentation.runOnMainSync { models.clear(); scope.cancel() } }
            root.deleteRecursively()
            preferences.forEach { base.deleteSharedPreferences(it) }
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
