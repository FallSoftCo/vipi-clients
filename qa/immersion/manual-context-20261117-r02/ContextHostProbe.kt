package co.fallsoft.vipi
import java.io.File
import org.json.JSONObject
import org.json.JSONArray
import kotlinx.coroutines.runBlocking
object ContextHostProbe { @JvmStatic fun main(args:Array<String>)=runBlocking {
    val fixture=JSONObject(File(args[0]).readText()).getJSONArray("cases");val rows=JSONArray()
    for(i in 0 until fixture.length()){
        val c=fixture.getJSONObject(i);val text=c.getString("text");val a=c.getInt("startUTF16");val b=c.getInt("endUTF16")
        val actual=ManualTranslationContext.enclosing(text,a,b,c.getString("language"))
        check(actual.text==c.getString("expectedContext")){"${c.getString("id")}: ${actual.text}"}
        check(actual.startUTF16==c.getInt("expectedStartUTF16")&&actual.endUTF16==c.getInt("expectedEndUTF16"))
        check(text.substring(actual.startUTF16,actual.endUTF16)==actual.text&&actual.startUTF16<=a&&actual.endUTF16>=b)
        rows.put(JSONObject().put("id",c.getString("id")).put("text",actual.text).put("start",actual.startUTF16).put("end",actual.endUTF16))
    }
    val text="Please book a table tonight.";val request=ManualTranslationRequest("book-context",text,7,11,"en","it","en",1,1)
    var translated="";val references=mutableListOf<String>()
    val result=ManualTranslationResolver.resolve(request,{true},{value,_,_->references+=value;if(value=="book")"Libro"else null},{"en"},{_,_->true},{value,_,_->translated=value;"Prenota un tavolo per stasera."},{_,_->null})
    check(result.status==ManualTranslationStatus.READY&&translated==text&&references.none{it=="book"})
    check(result.result!!.originalSlice=="book"&&result.result!!.sourceContextText==text&&result.result!!.contextExpanded)
    File(args[1]).writeText(JSONObject().put("passed",true).put("platform","Host JVM native BreakIterator component, not Android UI/model acceptance").put("cases",rows).put("isolated_dictionary_bypass_blocked",true).toString(2))
    println("Passed ${fixture.length()} context cases + isolated-reference guard")
}

}
