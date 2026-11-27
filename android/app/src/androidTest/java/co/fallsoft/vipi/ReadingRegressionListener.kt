package co.fallsoft.vipi

import android.content.Context
import android.os.Debug
import android.os.Process
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import org.json.JSONArray
import org.json.JSONObject
import org.junit.runner.Description
import org.junit.runner.Result
import org.junit.runner.notification.Failure
import org.junit.runner.notification.RunListener

/** Scope existing frozen fixture/output IO without changing reader assertions. */
internal fun readingRegressionFile(context: Context, name: String): File {
    require(name.matches(Regex("[A-Za-z0-9._-]+")))
    val run =
        InstrumentationRegistry.getArguments().getString("vipiReadingRegressionRun")
            ?: return File(context.filesDir, name)
    require(run.matches(Regex("(?:candidate-short|reading-status)-[0-9]{3}")))
    return File(File(context.filesDir, "reading-regression-$run"), name)
}

/**
 * AndroidJUnitRunner's documented -e listener observer. It never invokes a producer, mutates its
 * result or substitutes test UI; JUnit runs the original selected methods. The private checkpoints
 * permit an exact owned-PID abort.
 */
class ReadingRegressionListener : RunListener() {
    private data class Active(
        val id: String,
        val started: Long,
        val peakJava: AtomicLong,
        val peakRss: AtomicLong,
    )

    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private lateinit var owner: JSONObject
    private lateinit var directory: File
    private var expected = emptySet<String>()
    private val finished = mutableListOf<String>()
    private val failures = mutableListOf<String>()
    private val active = AtomicReference<Active?>()
    private val done = AtomicBoolean()
    private val samples = AtomicLong()
    private val monitorErrors = java.util.concurrent.CopyOnWriteArrayList<String>()
    private var monitor: Thread? = null

    @Synchronized
    private fun save(name: String, value: JSONObject) {
        val file = File(directory, name)
        val temporary = File(directory, ".$name.tmp")
        FileOutputStream(temporary).use { stream ->
            stream.write(value.toString(2).toByteArray(Charsets.UTF_8))
            stream.fd.sync()
        }
        Files.move(
            temporary.toPath(),
            file.toPath(),
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING,
        )
    }

    private fun memory(): JSONObject {
        val status = File("/proc/self/status").readLines()
        fun bytes(key: String) =
            status.single { it.startsWith("$key:") }.trim().split(Regex("\\s+"))[1].toLong() * 1024
        val runtime = Runtime.getRuntime()
        return JSONObject()
            .put("java_used", runtime.totalMemory() - runtime.freeMemory())
            .put("java_max", runtime.maxMemory())
            .put("rss", bytes("VmRSS"))
            .put("process_high_water_rss", bytes("VmHWM"))
            .put("native_allocated", Debug.getNativeHeapAllocatedSize())
    }

    override fun testRunStarted(description: Description) {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        val args = InstrumentationRegistry.getArguments()
        check(
            args.getString("vipiDedicatedEmulator") == "true" &&
                android.os.Build.MODEL.contains("sdk")
        )
        val run =
            requireNotNull(args.getString("vipiReadingRegressionRun")).also {
                require(it.matches(Regex("(?:candidate-short|reading-status)-[0-9]{3}")))
            }
        val nonce =
            requireNotNull(args.getString("vipiReaderNonce")).also {
                require(it.matches(Regex("[a-f0-9]{32}")))
            }
        val names = requireNotNull(args.getString("vipiReadingRegressionMethods")).split(',')
        require(
            names.size in 1..7 &&
                names.toSet().size == names.size &&
                names.all { it.matches(Regex("co\\.fallsoft\\.vipi\\.[A-Za-z]+#[A-Za-z]+")) }
        )
        expected = names.toSet()
        directory = File(context.filesDir, "reading-regression-$run")
        check(directory.isDirectory && !File(directory, "owner.json").exists())
        val fixtureArgument = args.getString("vipiReadingRegressionFixtureNames")
        val fixtures =
            if (fixtureArgument == "none") emptySet()
            else
                fixtureArgument
                    ?.split(',')
                    ?.filter { it.isNotEmpty() }
                    ?.also { names ->
                        check(
                            names.toSet().size == names.size &&
                                names.all { it.matches(Regex("[A-Za-z0-9._-]+")) }
                        )
                    }
                    ?.toSet()
                    ?: setOf(
                        "japanese-reading-candidate-protocol-r03b.json",
                        "japanese-kana-converter-protocol-r04.json",
                    )
        check(directory.listFiles()?.map { it.name }?.toSet() == fixtures) {
            "Only declared frozen inputs may precede this run"
        }
        val command =
            File("/proc/self/cmdline")
                .readBytes()
                .toString(Charsets.UTF_8)
                .substringBefore('\u0000')
        check(command == BuildConfig.APPLICATION_ID && Process.myUid() / 100_000 == 10)
        val ticks =
            File("/proc/self/stat")
                .readText()
                .substringAfterLast(") ")
                .trim()
                .split(Regex("\\s+"))[19]
        owner =
            JSONObject()
                .put("run", run)
                .put("nonce", nonce)
                .put("pid", Process.myPid())
                .put("uid", Process.myUid())
                .put("start_ticks", ticks)
                .put("cmdline", command)
        save("owner.json", owner)
        monitor =
            Thread(
                    {
                        while (!done.get()) {
                            try {
                                val m = memory()
                                val current = active.get()
                                samples.incrementAndGet()
                                current?.peakJava?.accumulateAndGet(m.getLong("java_used"), ::maxOf)
                                current?.peakRss?.accumulateAndGet(m.getLong("rss"), ::maxOf)
                                save(
                                    "progress.json",
                                    JSONObject(owner.toString())
                                        .put(
                                            "phase",
                                            if (current == null) "between_tests" else "running_test",
                                        )
                                        .put("test", current?.id ?: JSONObject.NULL)
                                        .put(
                                            "test_started_elapsed_ms",
                                            current?.started ?: JSONObject.NULL,
                                        )
                                        .put("memory", m)
                                        .put(
                                            "sampled_peak_java",
                                            current?.peakJava?.get() ?: JSONObject.NULL,
                                        )
                                        .put(
                                            "sampled_peak_rss",
                                            current?.peakRss?.get() ?: JSONObject.NULL,
                                        )
                                        .put("monitor_errors", JSONArray(monitorErrors)),
                                )
                                Thread.sleep(100)
                            } catch (_: InterruptedException) {
                                break
                            } catch (error: Exception) {
                                monitorErrors += error.toString()
                                break
                            }
                        }
                    },
                    "reading-regression-monitor",
                )
                .apply {
                    isDaemon = true
                    start()
                }
    }

    private fun id(description: Description) = "${description.className}#${description.methodName}"

    override fun testStarted(description: Description) {
        val id = id(description)
        check(id in expected && id !in finished && active.get() == null)
        val m = memory()
        val started = SystemClock.elapsedRealtime()
        active.set(
            Active(id, started, AtomicLong(m.getLong("java_used")), AtomicLong(m.getLong("rss")))
        )
        save(
            "test-${expected.sorted().indexOf(id)}.json",
            JSONObject(owner.toString())
                .put("test", id)
                .put("phase", "running")
                .put("started_elapsed_ms", started)
                .put("before", m),
        )
    }

    override fun testFailure(failure: Failure) {
        failures += "${id(failure.description)}: ${failure.exception}"
    }

    override fun testAssumptionFailure(failure: Failure) {
        failures += "ASSUMPTION: ${id(failure.description)}: ${failure.exception}"
    }

    override fun testIgnored(description: Description) {
        failures += "IGNORED: ${id(description)}"
    }

    override fun testFinished(description: Description) {
        val current = requireNotNull(active.get())
        check(current.id == id(description))
        val m = memory()
        current.peakJava.accumulateAndGet(m.getLong("java_used"), ::maxOf)
        current.peakRss.accumulateAndGet(m.getLong("rss"), ::maxOf)
        save(
            "test-${expected.sorted().indexOf(current.id)}.json",
            JSONObject(owner.toString())
                .put("test", current.id)
                .put("phase", "finished")
                .put("elapsed_ms", SystemClock.elapsedRealtime() - current.started)
                .put("after", m)
                .put("sampled_peak_java", current.peakJava.get())
                .put("sampled_peak_rss", current.peakRss.get()),
        )
        finished += current.id
        active.set(null)
    }

    override fun testRunFinished(result: Result) {
        done.set(true)
        monitor?.interrupt()
        monitor?.join(5_000)
        save(
            "summary.json",
            JSONObject(owner.toString())
                .put("expected", JSONArray(expected.sorted()))
                .put("finished", JSONArray(finished))
                .put("failures", JSONArray(failures))
                .put("junit_run_count", result.runCount)
                .put("junit_failure_count", result.failureCount)
                .put("junit_ignore_count", result.ignoreCount)
                .put("monitor_stopped", monitor?.isAlive == false)
                .put("monitor_samples", samples.get())
                .put("monitor_errors", JSONArray(monitorErrors))
                .put(
                    "complete",
                    finished.toSet() == expected &&
                        finished.size == expected.size &&
                        active.get() == null,
                )
                .put("assertions_passed", result.wasSuccessful() && failures.isEmpty())
                .put(
                    "scope",
                    "Exact selected reading regression methods; producer/cache/component scope is reported by each method. No unrelated UI journey or model acquisition.",
                ),
        )
    }
}
