package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** Synthetic/public QA text only. This cache is not the production private dictionary. */
@RunWith(AndroidJUnit4::class)
class TranslationPhraseDeviceTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { reader -> reader.readText() }
    }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Test fun recordIncrementalWholeAndPhraseTranslationsOffline() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val run = args.getString("vipiRunID") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val maximum = (args.getString("vipiMaxCases") ?: "10000").toInt()
        require(maximum in 1..10000)
        val context = instrumentation.targetContext
        val bytes = File(context.filesDir, "immersion-qa/phrase-protocol.json").readBytes()
        val protocol = JSONObject(bytes.toString(Charsets.UTF_8))
        check(protocol.getString("schema") == "vipi-local-phrase-probe-1")
        val samples = protocol.getJSONArray("samples")
        val extents = protocol.getJSONArray("window_extents")
        val cacheFile = File(context.filesDir, "phrase-cache-$run.sqlite")
        val db = SQLiteDatabase.openOrCreateDatabase(cacheFile, null)
        db.execSQL("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        db.execSQL("CREATE TABLE IF NOT EXISTS translations(source TEXT,target TEXT,input TEXT,output TEXT NOT NULL,latency_ms REAL NOT NULL,PRIMARY KEY(source,target,input))")
        db.execSQL("CREATE TABLE IF NOT EXISTS observations(ordinal INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
        val fingerprint = sha(bytes) + ":MLKit-17.0.3:qa-model-epoch-$run"
        db.rawQuery("SELECT value FROM metadata WHERE key='identity'", null).use {
            if (it.moveToFirst()) check(it.getString(0) == fingerprint) else db.execSQL("INSERT INTO metadata VALUES ('identity',?)", arrayOf(fingerprint))
        }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        var freshCalls = 0; var cacheHits = 0; var resumed = 0; var executed = 0
        try {
            shell("svc wifi disable"); shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork)
            LocalTranslation().use { translator ->
                suspend fun translate(text: String, source: String, target: String): String {
                    db.rawQuery("SELECT output FROM translations WHERE source=? AND target=? AND input=?", arrayOf(source,target,text)).use {
                        if (it.moveToFirst()) { cacheHits++; return it.getString(0) }
                    }
                    assertNull(network.activeNetwork)
                    val began = SystemClock.elapsedRealtimeNanos()
                    val output = withTimeout(45_000) { translator.translate(text,source,target) }
                    val elapsed = (SystemClock.elapsedRealtimeNanos()-began)/1_000_000.0
                    db.execSQL("INSERT INTO translations VALUES (?,?,?,?,?)", arrayOf<Any>(source,target,text,output,elapsed))
                    freshCalls++; return output
                }
                for (index in 0 until samples.length()) {
                    val exists = db.rawQuery("SELECT 1 FROM observations WHERE ordinal=?", arrayOf(index.toString())).use { it.moveToFirst() }
                    if (exists) { resumed++; continue }
                    if (executed >= maximum) break
                    val item = samples.getJSONObject(index); val original = item.getString("original")
                    val source = item.getString("source"); val target = item.getString("target")
                    val start = item.getInt("start"); val end = item.getInt("end")
                    require(original.substring(start,end) == item.getString("source_word"))
                    val began = SystemClock.elapsedRealtimeNanos()
                    val full = translate(original,source,target)
                    val words = LocalImmersion.words(original,source)
                    val first = words.indexOfFirst { it.last+1 > start && it.first < end }
                    val last = words.indexOfLast { it.first < end && it.last+1 > start }
                    require(first >= 0 && last >= first)
                    val ranges = linkedSetOf(start to end)
                    repeat(extents.length()) { at ->
                        val width = extents.getJSONArray(at)
                        val left = maxOf(0,first-width.getInt(0)); val right = minOf(words.lastIndex,last+width.getInt(1))
                        val a = minOf(start,words[left].first); val b = maxOf(end,words[right].last+1)
                        val text = original.substring(a,b)
                        if (right-left+1 <= protocol.getInt("maximum_window_words") &&
                            text.length <= protocol.getInt("maximum_phrase_characters") &&
                            !text.contains(Regex("[.!?。！？\\n]"))) ranges.add(a to b)
                    }
                    val targetWords = LocalImmersion.words(full,target)
                    val phrases = JSONArray()
                    for ((a,b) in ranges) {
                        val text = original.substring(a,b); val translated = translate(text,source,target)
                        val needle = translated.trim().trimEnd('.', '!', '?', '。', '！', '？').trimEnd()
                        val occurrences = JSONArray()
                        if (needle.isNotEmpty()) {
                            var at = full.indexOf(needle,ignoreCase=true)
                            while (at >= 0) {
                                val finish = at+needle.length
                                if (targetWords.any { it.first==at } && targetWords.any { it.last+1==finish })
                                    occurrences.put(JSONObject().put("start",at).put("end",finish).put("text",full.substring(at,finish)))
                                at = full.indexOf(needle,at+1,ignoreCase=true)
                            }
                        }
                        phrases.put(JSONObject().put("start",a).put("end",b).put("input",text).put("translation",translated)
                            .put("focus_only",a==start && b==end).put("whole_translation_matches",occurrences))
                    }
                    val row = JSONObject(item.toString()).put("translation",full).put("phrases",phrases)
                        .put("network_unavailable",network.activeNetwork==null).put("status","executed")
                        .put("latency_ms",(SystemClock.elapsedRealtimeNanos()-began)/1_000_000.0)
                    db.execSQL("INSERT INTO observations VALUES (?,?)",arrayOf<Any>(index,row.toString()))
                    executed++
                }
            }
            val rows = JSONArray()
            db.rawQuery("SELECT payload FROM observations ORDER BY ordinal",null).use {
                while (it.moveToNext()) rows.put(JSONObject(it.getString(0)))
            }
            val report = JSONObject().put("schema","vipi-local-phrase-observations-1").put("protocol_sha256",sha(bytes))
                .put("provider","MLKit 17.0.3").put("model_identity_limit","QA cache epoch; provider does not expose a content hash here")
                .put("cases_expected",samples.length()).put("cases_completed",rows.length()).put("complete",rows.length()==samples.length())
                .put("fresh_calls_this_run",freshCalls).put("cache_hits_this_run",cacheHits).put("resumed_cases",resumed)
                .put("network_absence_verified",true).put("linguistic_acceptance",false).put("runtime_integration",false).put("results",rows)
            File(context.filesDir,"phrase-observations-$run.json").writeText(report.toString(2))
            assertEquals(resumed+executed, rows.length())
        } finally {
            db.close()
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
        }
    }
}
