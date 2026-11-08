package co.fallsoft.vipi

import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

class NativeFullReadingDeviceTest {
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    @Test fun exactKoreanHostReplayOnNativeRuntime() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val bytes = File(context.filesDir, "android-korean-native-replay-r01.json").readBytes()
        assertEquals("7dace4e9781c3b504387aa5723d692b73a8ec300cc04c5459cc753d0e3a91de4", sha(bytes))
        val cases = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases"); assertEquals(38, cases.length())
        val rows = JSONArray(); val report = JSONObject().put("complete", false).put("input_sha256", sha(bytes)).put("cases", rows)
            .put("sdk", android.os.Build.VERSION.SDK_INT).put("translation_calls", 0).put("new_models", 0)
        val output = File(context.filesDir, "android-native-reading-replay-001.json")
        fun memory(): Int { val info = Debug.MemoryInfo(); Debug.getMemoryInfo(info); return info.totalPss }
        report.put("pss_before_kib", memory())
        try {
            for (index in 0 until cases.length()) {
                val sample = cases.getJSONObject(index); val text = sample.getString("source")
                val start = SystemClock.elapsedRealtimeNanos(); val value = KoreanReadings.resolve(text)
                val first = SystemClock.elapsedRealtimeNanos() - start; val warmStart = SystemClock.elapsedRealtimeNanos()
                val warm = KoreanReadings.resolve(text); val warmNs = SystemClock.elapsedRealtimeNanos() - warmStart
                val row = JSONObject().put("id", sample.getString("id")).put("first_ns", first).put("warm_ns", warmNs)
                    .put("reading", value.reading ?: JSONObject.NULL).put("issues", JSONArray(value.issues.toList()))
                rows.put(row)
                assertEquals(value, warm)
                assertEquals(if (sample.isNull("reading")) null else sample.getString("reading"), value.reading)
                assertEquals(sample.getString("inspection"), value.inspection)
                val issues = sample.getJSONArray("issues"); assertEquals((0 until issues.length()).map { issues.getString(it) }.toSet(), value.issues)
                val pieces = sample.getJSONArray("pieces"); assertEquals(pieces.length(), value.pieces.size)
                for ((i, piece) in value.pieces.withIndex()) {
                    val expected = pieces.getJSONObject(i)
                    assertEquals(expected.getInt("startUTF16"), piece.startUTF16); assertEquals(expected.getInt("endUTF16"), piece.endUTF16)
                    assertEquals(text.substring(piece.startUTF16, piece.endUTF16), piece.source)
                    assertEquals(expected.getString("source"), piece.source); assertEquals(expected.getString("rendered"), piece.rendered)
                    assertEquals(expected.getString("kind"), piece.kind); assertEquals(expected.getBoolean("insertedSeparator"), piece.insertedSeparator)
                    if (piece.kind != "converted") assertEquals(piece.source, piece.rendered)
                }
                if (value.pieces.isNotEmpty()) assertEquals(text, value.pieces.joinToString("") { it.source })
                row.put("exact_host_and_source_parity", true); output.writeText(report.toString(2))
            }
            report.put("complete", true)
        } finally { report.put("pss_after_kib", memory()); output.writeText(report.toString(2)) }
    }

    @Test fun defaultCoordinatorUsesAuthoredFirstCacheWithoutProviderOrModelDownloads() = runBlocking(Dispatchers.Default) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val bytes = File(context.filesDir, "android-default-reading-chat-plan-r01.json").readBytes()
        assertEquals("8fcd49364cd11df8920ee609c4e8ae829c6a04dd34acb6b096d92573fc5ba9d6", sha(bytes))
        val cases = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases"); val rows = JSONArray()
        val report = JSONObject().put("complete", false).put("default_producer", true).put("cases", rows).put("plan_sha256", sha(bytes))
        val output = File(context.filesDir, "android-native-reading-default-001.json")
        for (language in listOf("ja", "ko")) {
            val engine = ConversationImmersion(context, "en", language, .25)
            try {
                engine.checkDownloads(); report.put("${language}_translation_model_installed", engine.ready)
                for (i in 0 until cases.length()) {
                    val sample = cases.getJSONObject(i); if (sample.getString("language") != language) continue
                    val text = sample.getString("text"); val start = SystemClock.elapsedRealtimeNanos()
                    val first = engine.reading(text); val elapsed = SystemClock.elapsedRealtimeNanos() - start
                    assertEquals(sample.getString("reading"), first?.text); assertEquals(sample.getString("provenance"), first?.provenance?.name)
                    assertSame(first, engine.reading(text)); assertSame(first, engine.cachedReading(text))
                    rows.put(JSONObject().put("id", sample.getString("id")).put("reading", first!!.text).put("provenance", first.provenance.name)
                        .put("elapsed_ns", elapsed).put("same_cached_instance", true)); output.writeText(report.toString(2))
                }
                val unknown = if (language == "ja") "𠮷田さん。" else "漢字를 읽어요."
                assertNull(engine.reading(unknown)); assertNull(engine.reading(unknown)); assertNull(engine.reading("가".repeat(16385)))
                engine.close(); assertNull(engine.reading(cases.getJSONObject(0).getString("text")))
            } finally { engine.close() }
        }
        val license = context.assets.open("legal/upstream/unicode-cldr-f6925792-LICENSE.txt").use { it.readBytes() }
        assertEquals("65eb33419e22a297550a811b5b535f5e532f9a7e0114b516c0ea18afd53c3804", sha(license))
        report.put("unicode_license_sha256", sha(license)).put("complete", true); output.writeText(report.toString(2))
    }
}
