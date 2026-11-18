package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Rect
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
    createModel: (Application) -> VipiModel = { VipiModel(it, NoJourneyModelTranslation) }
) : AutoCloseable {
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    val base = instrumentation.targetContext
    val device: UiDevice = UiDevice.getInstance(instrumentation)
    private val application = base.applicationContext as Application
    private val prefix = "journey-${UUID.randomUUID()}-"
    private val root = File(base.cacheDir, prefix).apply { check(mkdirs()) }
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
            "co.fallsoft.vipi.uxqa", "co.fallsoft.vipi.sourcecontextqa"
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
    fun launch() {
        instrumentation.runOnMainSync { application.registerActivityLifecycleCallbacks(callback); installed = true }
        scenario = ActivityScenario.launch(Intent(base, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
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
    fun paragraphs(): List<StableImmersionText> {
        fun collect(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
            else -> emptyList()
        }
        return activity?.window?.decorView?.let(::collect).orEmpty()
    }
    fun fullyVisible(view: View): Boolean {
        val visible = Rect()
        return view.isShown && view.width > 0 && view.height > 0 && view.getLocalVisibleRect(visible) &&
            visible.left <= 0 && visible.top <= 0 && visible.right >= view.width && visible.bottom >= view.height
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
                views.put(JSONObject().put("original", view.displayedOriginal).put("drawn", view.visibleText())
                    .put("fully_visible", fullyVisible(view)).put("bounds", rect.toShortString()))
            }
            snapshot.put("native_paragraphs", views)
        }
        File(output, "$name.json").writeText(snapshot.toString(2))
    }
    fun stopActivity() {
        scenario?.close()
        scenario = null
    }
    override fun close() {
        stopActivity()
        instrumentation.runOnMainSync { if (installed) application.unregisterActivityLifecycleCallbacks(callback) }
        preferences.forEach { base.deleteSharedPreferences(it) }
        root.deleteRecursively()
    }
}

internal object NoJourneyModelTranslation : LanguageTranslation {
    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model download in app navigation tests")
    override suspend fun translate(text: String, source: String, target: String): String = error("No translation inference in app navigation tests")
    override fun close() = Unit
}
