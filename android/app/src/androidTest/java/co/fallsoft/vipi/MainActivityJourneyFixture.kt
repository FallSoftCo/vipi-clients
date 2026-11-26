package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Rect
import android.graphics.RectF
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/** Supplies isolated dependencies before the REAL activity resolves its normal
 * lazy ViewModel. No duplicate app router, private activity field or production hook. */
internal class MainActivityJourneyFixture(
    name: String,
    createModel: (Application) -> VipiModel = { VipiModel(it, NoJourneyModelTranslation) },
    private val retainedToken: String? = null
) : AutoCloseable {
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    val base = instrumentation.targetContext
    val device: UiDevice = UiDevice.getInstance(instrumentation)
    private val application = base.applicationContext as Application
    private val prefix = retainedToken?.let { token ->
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID in setOf("co.fallsoft.vipi.uxqa", "co.fallsoft.vipi.sourcecontextqa", "co.fallsoft.vipi.tutorialqa"))
        require(token.matches(Regex("[a-f0-9]{32}")))
        "journey-persistent-$token-"
    } ?: "journey-${UUID.randomUUID()}-"
    private var eraseRetainedOnClose = false
    private val root = File(base.cacheDir, prefix).apply {
        check(!java.nio.file.Files.isSymbolicLink(toPath()))
        check(parentFile.canonicalFile == base.cacheDir.canonicalFile)
        if (retainedToken == null) check(mkdirs()) else check((isDirectory || mkdirs()))
    }
    private val preferences = mutableSetOf<String>()
    val isolated = object : Application() {
        init { attachBaseContext(base) }
        override fun getApplicationContext(): Context = this
        override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        override fun getFilesDir() = File(root, "files").apply { mkdirs() }
        override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
            preferences += prefix + name
            return base.getSharedPreferences(prefix + name, mode)
        }
    }
    var model: VipiModel
        private set
    val output: File
    private var scenario: ActivityScenario<MainActivity>? = null
    private var activity: MainActivity? = null
    private var installed = false
    private var injectionCount = 0
    private val callback = object : Application.ActivityLifecycleCallbacks {
        override fun onActivityPreCreated(activity: Activity, savedInstanceState: Bundle?) {
            if (activity !is MainActivity) return
            val factory = object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    check(modelClass == VipiModel::class.java)
                    return model as T
                }
            }
            check(ViewModelProvider(activity, factory)[VipiModel::class.java] === model)
            injectionCount++
            this@MainActivityJourneyFixture.activity = activity
        }
        override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
        override fun onActivityStarted(activity: Activity) = Unit
        override fun onActivityResumed(activity: Activity) = Unit
        override fun onActivityPaused(activity: Activity) = Unit
        override fun onActivityStopped(activity: Activity) = Unit
        override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
        override fun onActivityDestroyed(activity: Activity) = Unit
    }
    init {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID in setOf(
            "co.fallsoft.vipi.uxqa", "co.fallsoft.vipi.sourcecontextqa", "co.fallsoft.vipi.tutorialqa", "co.fallsoft.vipi.groupsqa"
        )) { "Requires an explicitly isolated QA target; production is rejected" }
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val run = InstrumentationRegistry.getArguments().getString("vipiJourneyRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        output = File(base.filesDir, "journey-ui-$run/$name")
        check(!output.exists()) { "Use a fresh vipiJourneyRun; earlier journey evidence is retained" }
        check(output.mkdirs())
        var created: VipiModel? = null
        instrumentation.runOnMainSync { created = createModel(isolated) }
        model = requireNotNull(created)
    }
    fun launch(data: android.net.Uri? = null) {
        instrumentation.runOnMainSync { application.registerActivityLifecycleCallbacks(callback); installed = true }
        scenario = ActivityScenario.launch(Intent(base, MainActivity::class.java).apply {
            if (data != null) { action = Intent.ACTION_VIEW; setData(data) }
        }.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        check(injectionCount == 1) { "The real MainActivity must use the isolated model before onCreate" }
    }
    fun recreate() {
        val before = injectionCount
        requireNotNull(scenario).recreate()
        check(injectionCount == before + 1)
    }
    /** New owner/model over the same private disk, after the real activity's
     * ViewModelStore has closed the previous owner. No session reseeding. */
    fun relaunch(createModel: (Application) -> VipiModel) {
        stopActivity()
        instrumentation.runOnMainSync { model = createModel(isolated) }
        val before = injectionCount
        scenario = ActivityScenario.launch(Intent(base, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        check(injectionCount == before + 1)
    }
    fun backgroundAndResume() {
        requireNotNull(scenario).moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
        requireNotNull(scenario).moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
    }
    fun paragraphs(): List<FullMessageTextView> {
        fun collect(view: View): List<FullMessageTextView> = when (view) {
            is FullMessageTextView -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
            else -> emptyList()
        }
        return activity?.window?.decorView?.let(::collect).orEmpty()
    }
    private data class CaptureGeometry(val timeline: RectF, val editor: RectF)
    private var captureGeometry: (() -> CaptureGeometry?)? = null
    /** Read actual clipped Compose geometry outside runOnMainSync. A native
     * AndroidView can report local visibility behind Compose siblings. */
    fun bindConversationCapture(compose: androidx.compose.ui.test.junit4.ComposeTestRule, inputTag: String) {
        captureGeometry = {
            val timelines = compose.onAllNodes(androidx.compose.ui.test.SemanticsMatcher("Actual conversation LazyColumn") {
                it.config.contains(androidx.compose.ui.semantics.SemanticsActions.ScrollToIndex)
            }, useUnmergedTree = true).fetchSemanticsNodes().filter { it.boundsInWindow.width > 0 && it.boundsInWindow.height > 0 }
            val editors = compose.onAllNodes(androidx.compose.ui.test.SemanticsMatcher.expectValue(
                androidx.compose.ui.semantics.SemanticsProperties.TestTag, inputTag), useUnmergedTree = true).fetchSemanticsNodes()
            if (timelines.size != 1 || editors.size != 1) null else {
                val list = timelines.single().boundsInWindow; val editor = editors.single().boundsInWindow
                CaptureGeometry(RectF(list.left, list.top, list.right, list.bottom), RectF(editor.left, editor.top, editor.right, editor.bottom))
            }
        }
    }
    private fun fullyVisible(view: View, full: Rect, viewport: RectF?, window: Rect): Boolean {
        val reported = Rect()
        return viewport != null && view.isShown && view.hasWindowFocus() && view.alpha == 1f &&
            view.width > 0 && view.height > 0 && view.getGlobalVisibleRect(reported) && reported.contains(full) &&
            viewport.contains(RectF(full)) && window.contains(full)
    }
    fun hideKeyboard() {
        instrumentation.runOnMainSync { requireNotNull(activity).window.insetsController?.hide(android.view.WindowInsets.Type.ime()) }
    }
    fun unobscuredWindow(): Rect {
        var visible: Rect? = null
        instrumentation.runOnMainSync {
            val host = requireNotNull(activity)
            val bounds = host.windowManager.currentWindowMetrics.bounds
            val insets = requireNotNull(host.window.decorView.rootWindowInsets)
                .getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
            visible = Rect(bounds.left + insets.left, bounds.top + insets.top,
                bounds.right - insets.right, bounds.bottom - insets.bottom)
        }
        return requireNotNull(visible)
    }
    fun capture(name: String) {
        instrumentation.waitForIdleSync()
        check(device.takeScreenshot(File(output, "$name.png")))
        device.dumpWindowHierarchy(File(output, "$name.xml"))
        val snapshot = JSONObject()
        val window = unobscuredWindow()
        val geometry = runCatching { captureGeometry?.invoke() }.onFailure {
            snapshot.put("visibility_geometry_error", it.toString())
                .put("visibility_geometry_stack", it.stackTraceToString().take(16_384))
        }.getOrNull()
        snapshot.put("visibility_qualification", if (geometry == null) "unqualified_no_unique_actual_compose_viewport" else "actual_compose_timeline_editor_window_IME_intersection")
            .put("unobscured_window", window.toShortString())
        instrumentation.runOnMainSync {
            snapshot.put("screen", model.screen.name).put("known", model.knownLanguage).put("learning", model.targetLanguage)
                .put("activity_injections", injectionCount).put("actual_activity", activity?.javaClass?.name)
                .put("width_px", base.resources.displayMetrics.widthPixels)
                .put("height_px", base.resources.displayMetrics.heightPixels)
                .put("screen_width_dp", base.resources.configuration.screenWidthDp)
                .put("font_scale", base.resources.configuration.fontScale.toDouble())
                .put("target_files_dir", base.filesDir.absolutePath)
            val views = JSONArray()
            paragraphs().forEach { view ->
                val rect = Rect(); view.getGlobalVisibleRect(rect)
                val screen = IntArray(2); val localWindow = IntArray(2)
                view.getLocationOnScreen(screen); view.getLocationInWindow(localWindow)
                val full = Rect(screen[0], screen[1], screen[0] + view.width, screen[1] + view.height)
                val viewport = geometry?.let {
                    val dx = (screen[0] - localWindow[0]).toFloat(); val dy = (screen[1] - localWindow[1]).toFloat()
                    RectF(maxOf(it.timeline.left + dx, window.left.toFloat()), maxOf(it.timeline.top + dy, window.top.toFloat()),
                        minOf(it.timeline.right + dx, window.right.toFloat()), minOf(it.timeline.bottom + dy, it.editor.top + dy, window.bottom.toFloat()))
                }
                views.put(JSONObject().put("original", view.originalMessage).put("drawn", view.text.toString())
                    .put("fully_visible", fullyVisible(view, full, viewport, window)).put("bounds", rect.toShortString())
                    .put("native_full_bounds", full.toShortString()).put("actual_compose_content_viewport", viewport?.toString() ?: JSONObject.NULL))
            }
            snapshot.put("native_paragraphs", views)
        }
        File(output, "$name.json").writeText(snapshot.toString(2))
    }
    /** ActivityScenario identifies its activity by its original Intent. A real
     * notification tap changes that Intent via MainActivity.onNewIntent. Finish
     * the captured activity itself and verify destruction before releasing it. */
    fun finishAfterExternalIntent() {
        val current = activity ?: return stopActivity()
        instrumentation.runOnMainSync { if (!current.isDestroyed) current.finishAndRemoveTask() }
        val until = android.os.SystemClock.elapsedRealtime() + 8_000
        while (!current.isDestroyed && android.os.SystemClock.elapsedRealtime() < until) android.os.SystemClock.sleep(30)
        check(current.isDestroyed)
        scenario = null
    }

    fun stopActivity() {
        scenario?.close()
        scenario = null
    }
    /** Called only after the retained journey verifies its exact ownership
     * ledger and terminal proof. Failures keep their private disk for diagnosis. */
    fun eraseRetainedStorageAfterProof(token: String) {
        check(retainedToken != null && token == retainedToken)
        eraseRetainedOnClose = true
    }
    override fun close() {
        stopActivity()
        instrumentation.runOnMainSync { if (installed) application.unregisterActivityLifecycleCallbacks(callback) }
        if (retainedToken == null || eraseRetainedOnClose) {
            preferences.forEach { base.deleteSharedPreferences(it) }
            check(!java.nio.file.Files.isSymbolicLink(root.toPath()))
            root.deleteRecursively()
        }
    }
}

internal object NoJourneyModelTranslation : LanguageTranslation {
    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model download in app navigation tests")
    override suspend fun translate(text: String, source: String, target: String): String = error("No translation inference in app navigation tests")
    override fun close() = Unit
}
