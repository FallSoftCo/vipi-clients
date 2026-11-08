package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.Instant

/** Paired runtime qualification of frozen reviewed inputs; not a new blind language benchmark. */
class SourceUnitStarterDeviceTest {
    companion object {
        const val NATIVE_LITERAL_GUARD_SHA="561f557cbd6b9ce2b02fc694ea9fec239a7d78e462705c127eb1f4c2343c6338"
        const val PROTOCOL_SHA="fd89fd2bf9988b657fe3f8d689f23d5554364c9c5b73675ac80ebf6a6f2e3ec6"
        const val PACK_FILE="reviewed-source-unit-native-candidate-r02.json"
        const val PROTOCOL_FILE="source-unit-starter-native-protocol-r01.json"
    }
    private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
    private fun shell(command:String)=instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
    }
    private fun counters(c:ImmersionInvocationCounters)=JSONObject().put("model_readiness_calls",c.readiness)
        .put("heavy_alignment_calls",c.heavyAlignment).put("source_partial_presentation_calls",c.partialPresentation)
        .put("qa_source_lookup_calls",c.qaSourceLookup)
    private fun presentation(value:ImmersionPresentation?)=JSONObject()
        .put("original",value?.original ?: JSONObject.NULL).put("complete_translation",value?.translation ?: JSONObject.NULL)
        .put("mixed",value?.let { ImmersionText.project(it) } ?: JSONObject.NULL)
        .put("spans",JSONArray(value?.spans?.map { span -> JSONObject().put("original",span.original)
            .put("translated",span.translated).put("reading",span.romanization ?: JSONObject.NULL)
            .put("source_start_utf16",span.start).put("source_end_utf16",span.end)
            .put("target_start_utf16",span.targetStart).put("target_end_utf16",span.targetEnd) } ?: emptyList<JSONObject>()))
        .put("references",JSONArray((value as? PartialImmersionResult)?.references?.map { unit -> JSONObject()
            .put("id",unit.referenceId).put("catalog_sha256",unit.catalogSha256).put("original",unit.original)
            .put("target",unit.translated).put("reading",unit.reading ?: JSONObject.NULL)
            .put("source_start_utf16",unit.start).put("source_end_utf16",unit.end).put("native_source_tokens",unit.nativeSourceTokens) } ?: emptyList<JSONObject>()))
    private class Tracking(private val network:ConnectivityManager):LanguageTranslation {
        private val native=LocalTranslation();val calls=JSONArray()
        override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model downloads")
        override suspend fun translate(text:String,source:String,target:String):String {
            assertNull(network.activeNetwork)
            val row=JSONObject().put("source",source).put("target",target).put("input",text);calls.put(row)
            val began=SystemClock.elapsedRealtimeNanos()
            try { return withTimeout(30_000) { native.translate(text,source,target) }.also {
                row.put("translation",it).put("identifiers_preserved",TranslationIntegrity.preservesIdentifiers(text,it))
            } } catch(error:Throwable) { row.put("error",error.javaClass.simpleName);throw error }
            finally { row.put("elapsed_ms",(SystemClock.elapsedRealtimeNanos()-began)/1e6);assertNull(network.activeNetwork) }
        }
        override fun close()=native.close()
    }
    @Test fun captureBaseline():Unit=runBlocking { capture(false) }
    @Test fun captureCandidate():Unit=runBlocking { capture(true) }
    private suspend fun capture(enabled:Boolean) {
        val args=InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator")=="true")
        check(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val producerSourceSha=requireNotNull(args.getString("vipiStarterProducerSha"));require(producerSourceSha.matches(Regex("[a-f0-9]{64}")))
        val run=args.getString("vipiStarterRun") ?: "001";require(run.matches(Regex("[0-9]{3}")))
        val context=instrumentation.targetContext
        val bytes=File(context.filesDir,PROTOCOL_FILE).readBytes();assertEquals(PROTOCOL_SHA,ReviewedSourceUnitQa.sha(bytes))
        val pack=File(context.filesDir,PACK_FILE).readBytes();assertEquals(ReviewedSourceUnitQa.SHA256,ReviewedSourceUnitQa.sha(pack))
        val protocol=JSONObject(bytes.toString(Charsets.UTF_8));val input=protocol.getJSONArray("cases");assertEquals(240,input.length())
        val arm=if(enabled) "candidate" else "baseline"
        val baseline=File(context.filesDir,"source-unit-starter-baseline-$run.json")
        if(enabled) {
            val control=JSONObject(baseline.readText());assertTrue(control.getBoolean("complete"))
            assertEquals(PROTOCOL_SHA,control.getString("input_sha256"));assertFalse(control.getBoolean("starter_enabled"))
        }
        val output=File(context.filesDir,"source-unit-starter-$arm-$run.json");check(!output.exists())
        val report=JSONObject().put("schema","vipi-native-source-starter-capture-1").put("complete",false)
            .put("native_literal_guard_source_sha256",NATIVE_LITERAL_GUARD_SHA).put("qa_producer_source_sha256",producerSourceSha)
            .put("arm",arm).put("starter_enabled",enabled).put("production",false).put("blind_validation",false)
            .put("input_sha256",PROTOCOL_SHA).put("pack_sha256",ReviewedSourceUnitQa.SHA256).put("pack_version",ReviewedSourceUnitQa.VERSION)
            .put("catalog_sha256",context.assets.open("immersion/catalog.json").use { ReviewedSourceUnitQa.sha(it.readBytes()) })
            .put("started_at",Instant.now().toString()).put("translation_provider","Google MLKit17.0.3 actual installed local models")
            .put("download_calls",0).put("counter_scope","Actual production ConversationImmersion invocation callbacks; explicit DEBUG-only starter injection")
            .put("timing_scope","Per-pair fresh engine, native tokenization before each first timed request; installed models, not global cold startup")
        val pairs=JSONArray();val rows=JSONArray();val memory=JSONArray();report.put("pairs",pairs).put("cases",rows).put("process_memory",memory)
        fun sampleMemory(stage:String) { val info=Debug.MemoryInfo();Debug.getMemoryInfo(info)
            memory.put(JSONObject().put("stage",stage).put("total_pss_kib",info.totalPss).put("total_private_dirty_kib",info.totalPrivateDirty)
                .put("java_heap_used_bytes",Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory()).put("elapsed_ms",SystemClock.elapsedRealtime())) }
        fun save() { val tmp=File(output.parentFile,output.name+".tmp");tmp.writeText(report.toString(2));check(tmp.renameTo(output)) }
        val network=context.getSystemService(ConnectivityManager::class.java)
        val wifi=shell("settings get global wifi_on").trim();val mobile=shell("settings get global mobile_data").trim()
        report.put("wifi_before",wifi).put("mobile_before",mobile);save()
        try {
            shell("svc wifi disable");shell("svc data disable")
            withTimeout(15_000) { while(network.activeNetwork!=null) delay(100) };assertNull(network.activeNetwork)
            report.put("offline_network_observation","Both emulator radios disabled; activeNetwork null before/after actual provider calls")
            sampleMemory("start")
            withTimeout(1_800_000) { for(target in listOf("sw","ja","es")) {
                val init=SystemClock.elapsedRealtimeNanos();val policy=if(enabled) ReviewedSourceUnitQa(pack) else null
                val tracking=Tracking(network);val engine=ConversationImmersion(context,"en",target,.10,tracking,policy)
                val pair=JSONObject().put("source","en").put("target",target).put("engine_and_policy_init_ms",(SystemClock.elapsedRealtimeNanos()-init)/1e6)
                pairs.put(pair)
                try {
                    val readyStart=SystemClock.elapsedRealtimeNanos();engine.checkDownloads()
                    pair.put("already_installed_models_ready",engine.ready).put("model_status_check_ms",(SystemClock.elapsedRealtimeNanos()-readyStart)/1e6);save()
                    val selected=(0 until input.length()).map { input.getJSONObject(it) }.filter { it.getString("target")==target };assertEquals(80,selected.size)
                    for((index,sourceCase) in selected.withIndex()) {
                        assertEquals("en",sourceCase.getString("source"));assertEquals(.10,sourceCase.getDouble("requested_density"),0.0)
                        val text=sourceCase.getString("text");val nativeWords=LocalImmersion.words(text,"en")
                        val row=JSONObject(sourceCase.toString()).put("native_source_word_ranges_utf16",JSONArray(nativeWords.map { JSONArray(listOf(it.first,it.last+1)) }))
                            .put("actual_native_token_budget",maxOf(1,(nativeWords.size*.10).toInt()))
                        rows.put(row);save()
                        for(phase in listOf("first","warm")) {
                            val before=tracking.calls.length();val start=SystemClock.elapsedRealtimeNanos()
                            val observation=JSONObject();row.put(phase,observation)
                            try {
                                val result=engine.presentation(text,"en")
                                observation.put("elapsed_ms",(SystemClock.elapsedRealtimeNanos()-start)/1e6)
                                    .put("status",engine.lastOutcome?.status?.name).put("fallback_status",engine.lastOutcome?.fallbackStatus?.name)
                                    .put("origin",engine.lastOutcome?.origin?.name).put("cache_hit",engine.lastOutcome?.cacheHit)
                                    .put("counters",counters(engine.lastInvocation)).put("result",presentation(result))
                                if(phase=="first") row.put("source_candidate_diagnostics",if(engine.lastInvocation.qaSourceLookup>0) policy?.lastDiagnostic else JSONObject().put("called",false))
                                val spans=result?.spans ?: emptyList()
                                val changed=nativeWords.count { word -> spans.any { it.start<=word.first && it.end>word.last } }
                                observation.put("actual_changed_source_words",changed).put("actual_changed_depth",if(nativeWords.isEmpty()) 0.0 else changed.toDouble()/nativeWords.size)
                                if(result is PartialImmersionResult) {
                                    assertTrue(SourceReferencePresentation.isAnchored(result,target));assertNull(result.translation)
                                    if(result.references.any { it.catalogSha256==ReviewedSourceUnitQa.SHA256 }) {
                                        assertTrue(enabled);assertEquals(1,spans.size);assertTrue(changed<=row.getInt("actual_native_token_budget"))
                                        assertEquals(0,tracking.calls.length()-before);assertEquals(0,engine.lastInvocation.readiness);assertEquals(0,engine.lastInvocation.heavyAlignment)
                                        if(target=="ja") assertTrue(spans.all { !it.romanization.isNullOrBlank() })
                                    }
                                }
                            } catch(error:Exception) { observation.put("error",error.javaClass.simpleName);if(error is CancellationException) throw error }
                            finally { observation.put("translation_calls",tracking.calls.length()-before)
                                .put("raw_provider_calls",JSONArray((before until tracking.calls.length()).map { tracking.calls.getJSONObject(it) }));save() }
                        }
                        row.put("complete",true);save();if(index==39) { sampleMemory("$target-midpoint");save() }
                    }
                } finally { engine.close();sampleMemory("$target-complete");save() }
            } }
            report.put("complete",true).put("finished_at",Instant.now().toString());save()
        } finally {
            shell("svc wifi ${if(wifi=="1") "enable" else "disable"}");shell("svc data ${if(mobile=="1") "enable" else "disable"}")
            report.put("wifi_after",shell("settings get global wifi_on").trim()).put("mobile_after",shell("settings get global mobile_data").trim());save()
        }
    }
}
