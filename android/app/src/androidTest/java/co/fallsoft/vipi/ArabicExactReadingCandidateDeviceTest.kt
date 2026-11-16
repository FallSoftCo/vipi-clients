package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import android.os.Debug
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.util.zip.InflaterInputStream

/** Isolated read-only candidate probe. Does not register a production reading provider. */
class ArabicExactReadingCandidateDeviceTest {
 @Test fun exactLookupAndResourceCost() {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true");val dir=File(inst.targetContext.filesDir,"arabic-exact-reading-candidate-r01");val src=File(dir,"candidate.sqlite.zlib");val dbFile=File(dir,"candidate.sqlite");val out=File(dir,"report.json");check(!dbFile.exists()&&!out.exists())
  fun sha(file:File)=MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString(""){"%02x".format(it)}
  fun pss():Int=Debug.MemoryInfo().also{Debug.getMemoryInfo(it)}.totalPss
  assertEquals(929775,src.length());assertEquals("b2c539dc86e85b2706b045cb7efb0f8279d39a8f10322c90732ff5fb17880cc4",sha(src));val before=pss();val start=System.nanoTime()
  InflaterInputStream(src.inputStream()).use { input -> dbFile.outputStream().use { output -> input.copyTo(output) } };val inflateMs=(System.nanoTime()-start)/1e6
  assertEquals(6008832,dbFile.length());assertEquals("bc5e480b551eb6da067b7dee36833d405cbe01221eca13e65d6a4faebf766eae",sha(dbFile))
  val began=System.nanoTime();val db=SQLiteDatabase.openDatabase(dbFile.path,null,SQLiteDatabase.OPEN_READONLY);val openMs=(System.nanoTime()-began)/1e6;val rows=JSONArray();val timings=mutableListOf<Double>()
  try {
   val samples=linkedMapOf("كوب" to "kūb","مدينة" to "madīna","موسيقى" to "mūsīqā","ضع" to null,"بالوعة" to null,"كوبx" to null,"كُوب" to null,"كتاب" to null)
   for((surface,expected) in samples) {
    val t=System.nanoTime();val result=db.rawQuery("SELECT reading FROM readings WHERE surface=?",arrayOf(surface)).use{c->if(c.moveToFirst())c.getString(0).also{assertFalse(c.moveToNext())} else null};val elapsed=(System.nanoTime()-t)/1e6;timings+=elapsed;assertEquals(surface,expected,result)
    rows.put(JSONObject().put("source_exact",surface).put("reading",result?:JSONObject.NULL).put("lookup_ms",elapsed))
   }
   val sorted=timings.sorted();JSONObject().put("complete",true).put("active",false).put("schema","qa-arabic-exact-reading-1").put("compressed_sha256",sha(src)).put("expanded_sha256",sha(dbFile)).put("compressed_bytes",src.length()).put("expanded_bytes",dbFile.length()).put("inflate_ms",inflateMs).put("sqlite_open_ms",openMs).put("lookup_median_ms",(sorted[3]+sorted[4])/2).put("lookup_max_ms",sorted.last()).put("process_pss_before_kib",before).put("process_pss_after_kib",pss()).put("samples",rows).put("limitations","exact approved headwords only; no semantic or pronunciation acceptance; memory measurements are noisy process snapshots").also{out.writeText(it.toString(2))}
  } finally {db.close()}
 }
}
