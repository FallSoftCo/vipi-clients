package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

@RunWith(AndroidJUnit4::class)
class ContextIndexDeviceTest {
    @Test fun attestedContextIndexOnNativeSQLite() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = File(context.filesDir, "context-index-001")
        val expected = JSONObject(File(fixture, "native-queries.json").readText())
        val file = File(fixture, "contexts.sqlite")
        assertEquals(expected.getLong("database_bytes"), file.length())
        val hash = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }
        assertEquals(expected.getString("database_sha256"), hash)
        val elapsed = mutableListOf<Double>(); val pairs = mutableSetOf<String>(); var version = ""
        val sql = "SELECT e.id,e.target FROM context_search JOIN examples e ON e.id=context_search.docid WHERE context_search MATCH ? AND e.source_language=? AND e.target_language=? AND e.source_key=? ORDER BY e.id LIMIT 8"
        SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
            db.rawQuery("SELECT sqlite_version()", null).use { assertTrue(it.moveToFirst()); version = it.getString(0) }
            val queries = expected.getJSONArray("queries")
            repeat(queries.length()) { index ->
                val query = queries.getJSONObject(index)
                val begin = SystemClock.elapsedRealtimeNanos(); val observed = mutableListOf<Pair<Long, String>>()
                db.rawQuery(sql, arrayOf(query.getString("query"), query.getString("source"), query.getString("target"), query.getString("source_key"))).use { cursor ->
                    while (cursor.moveToNext()) observed.add(cursor.getLong(0) to cursor.getString(1))
                }
                elapsed.add((SystemClock.elapsedRealtimeNanos()-begin)/1_000_000.0)
                val rows = query.getJSONArray("expected")
                val wanted = (0 until rows.length()).map { rows.getJSONObject(it).let { row -> row.getLong("id") to row.getString("target") } }
                assertEquals(wanted, observed)
                pairs.add(query.getString("source") + "-" + query.getString("target"))
            }
        }
        assertEquals(expected.getInt("pairs"), pairs.size); assertTrue(elapsed.isNotEmpty())
        val sorted = elapsed.sorted()
        File(context.filesDir, "context-index-native.json").writeText(JSONObject()
            .put("queries", elapsed.size).put("pairs", pairs.size).put("query_ms", JSONArray(elapsed))
            .put("median_ms", sorted[sorted.size/2]).put("p95_ms", sorted[minOf(sorted.lastIndex, (sorted.size*0.95).toInt())])
            .put("sqlite_version", version).put("database_sha256", hash).put("linguistic_acceptance", false)
            .put("evidence", "attested-example self-retrieval, not independent meaning selection").toString(2))
    }
}
