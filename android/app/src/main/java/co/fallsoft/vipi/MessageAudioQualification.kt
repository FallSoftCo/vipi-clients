package co.fallsoft.vipi

import android.os.SystemClock
import org.json.JSONObject

/** In-memory native QA observation only. Release/production packages cannot
 * attach or emit; this is never product telemetry or persistent logging. */
internal object MessageAudioQualification {
    private val allowed: Boolean get() = BuildConfig.DEBUG && BuildConfig.APPLICATION_ID in
        setOf("co.fallsoft.vipi.sourcecontextqa", "co.fallsoft.vipi.uxqa")
    @Volatile private var observer: ((JSONObject) -> Unit)? = null
    fun attach(value: ((JSONObject) -> Unit)?) { check(allowed); observer = value }
    fun emit(stage: String, id: String? = null, vararg fields: Pair<String, Any?>) {
        if (!allowed) return
        val sink = observer ?: return
        runCatching {
            val event = JSONObject().put("stage", stage).put("id", id ?: JSONObject.NULL)
                .put("uptime_ms", SystemClock.uptimeMillis()).put("thread", Thread.currentThread().name)
            fields.forEach { (key, value) -> event.put(key, value ?: JSONObject.NULL) }
            sink(event)
        }
    }
}
