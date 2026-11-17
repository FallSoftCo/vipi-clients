package co.fallsoft.vipi
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
fun main(){
    val q=File("qa/immersion/arabic-diacritization-20261117-r01")
    val cases=JSONObject(File(q,"renderer-regressions.json").readText()).getJSONArray("cases");val rows=JSONArray()
    for(i in 0 until cases.length()){
        val c=cases.getJSONObject(i);val text=c.getString("text");val expected=if(c.isNull("expected"))null else c.getString("expected")
        val result=ArabicVocalizedReadings.resolve(text)
        check(expected==result.reading){"${c.getString("id")}: ${result.reading} != $expected"}
        check(result.pieces.joinToString(""){it.source}==text)
        check(result.pieces.filter{it.protected}.all{it.source==it.reading})
        rows.put(JSONObject().put("id",c.getString("id")).put("source",text).put("reading",result.reading?:JSONObject.NULL).put("partition_exact",true))
    }
    val candidate=JSONObject(File(q,"qualification-results-r02.json").readText()).getJSONArray("cases");val inferred=JSONArray()
    for(i in 0 until candidate.length()){
        val row=candidate.getJSONObject(i);val result=ArabicVocalizedReadings.resolve(row.getString("preserving_derived_metadata"))
        inferred.put(JSONObject().put("id",row.getString("id")).put("category",row.getString("category")).put("model_script",row.getString("preserving_derived_metadata")).put("candidate_reading",result.reading?:JSONObject.NULL))
    }
    File(q,"renderer-jvm-results.json").writeText(JSONObject().put("platform","Host JVM, dormant native Kotlin renderer component; not Android execution")
        .put("passed",true).put("regressions",rows).put("unaccepted_model_inference_readings",inferred).toString(2))
    println("Passed ${cases.length()} Kotlin renderer regressions")
}
