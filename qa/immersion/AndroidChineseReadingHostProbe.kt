package co.fallsoft.vipi
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.security.MessageDigest
private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
fun main(args: Array<String>) {
    require(args.size == 3); val data=File(args[0]).readBytes(); val input=File(args[1]).readBytes(); val output=File(args[2]); check(!output.exists())
    val start=System.nanoTime(); val reader=ChineseReadings(data); val loaded=System.nanoTime()-start
    val cases=JSONObject(input.toString(Charsets.UTF_8)).getJSONArray("cases"); val rows=JSONArray()
    fun encode(value: ChineseReadings.Result) = JSONObject().put("reading",value.reading?:JSONObject.NULL)
        .put("pieces",JSONArray(value.pieces.map { p -> JSONObject().put("source",p.source).put("reading",p.reading).put("start_utf16",p.startUTF16)
            .put("end_utf16",p.endUTF16).put("converted",p.converted).put("protected",p.protected) }))
        .put("unresolved_utf16",JSONArray(value.unresolved.map { JSONArray(listOf(it.first,it.last+1)) }))
    for(i in 0 until cases.length()) {
        val c=cases.getJSONObject(i);val text=if(c.has("text")) c.getString("text") else c.getString("source")
        val raw=reader.resolve(text,false);val began=System.nanoTime();val first=reader.resolve(text);val elapsed=System.nanoTime()-began
        val warm=reader.resolve(text);check(first==warm)
        rows.put(JSONObject().put("id",c.getString("id")).put("source",text).put("raw_parity",encode(raw)).put("first",encode(first)).put("warm",encode(warm)).put("first_ns",elapsed))
    }
    output.writeText(JSONObject().put("complete",true).put("cases",rows).put("input_sha256",hash(input)).put("data_sha256",hash(data))
        .put("load_ms",loaded/1e6).put("elapsed_ms",(System.nanoTime()-start)/1e6).put("platform","Host JVM21, not Android")
        .put("memory",JSONArray(File("/proc/self/status").readLines().filter { it.startsWith("VmHWM:") || it.startsWith("VmRSS:") })).toString(2))
}
