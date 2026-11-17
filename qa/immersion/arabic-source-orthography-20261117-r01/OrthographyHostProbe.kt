package co.fallsoft.vipi.core
import org.json.*
import java.io.File
object OrthographyHostProbe {
 @JvmStatic fun main(args:Array<String>) {
  val cases=JSONObject(File(args[0]).readText()).getJSONArray("cases")
  val rows=JSONArray()
  for(i in 0 until cases.length()) {
   val c=cases.getJSONObject(i);val text=c.getString("text");val a=c.getInt("startUTF16");val b=c.getInt("endUTF16")
   val allowed=SourceOrthography.permitsReplacement(text,a,b)
   check(allowed==c.getBoolean("allowed")){c.getString("id")}
   rows.put(JSONObject().put("id",c.getString("id")).put("allowed",allowed))
  }
  fun checkRange(text:String,a:Int,b:Int,target:String,allowed:Boolean) {
   val surface=text.substring(a,b)
   for(scoped in listOf(false,true)) {
    val entry=VocabularyEntry(surface,listOf(target),sourceScope=if(scoped)VocabularySourceScope(text,a,b)else null)
    val result=ImmersionEngine().align(text,target,listOf(entry),1.0,"en",setOf(a,b),sourceTokenCount=8)
    check(result.spans.isNotEmpty()==allowed){"core source admission $surface scoped=$scoped"}
   }
   val unit=SourceReferenceUnit(a,b,surface,target,null,"qa","a".repeat(64),1)
   val partial=SourceReferencePresentation.create(text,"en",listOf(unit),1.0,8)
   check((partial!=null)==allowed){"partial admission $surface"}
   if(partial!=null)check(ImmersionText.project(partial,partial.spans.map{it.id}.toSet())==text)
  }
  checkRange("أنا أشرب الماء الآن.",11,14,"water",false)
  checkRange("أنا أشرب الماء الآن.",9,14,"water",true)
  checkRange("أنا أحب الموسيقى.",10,16,"music",false)
  checkRange("أنا أحب الموسيقى.",8,16,"music",true)
  val mixed="الماء كتاب"
  val p=checkNotNull(SourceReferencePresentation.create(mixed,"en",listOf(SourceReferenceUnit(2,5,"ماء","water",null,"bad","a".repeat(64),1),SourceReferenceUnit(6,10,"كتاب","book",null,"good","a".repeat(64),1)),1.0,2))
  check(p.spans.single().original=="كتاب"&&ImmersionText.project(p,p.spans.map{it.id}.toSet())==mixed)
  check(!SourceOrthography.permitsReplacement("😀ماء",1,2))
  File(args[1]).writeText(JSONObject().put("passed",true).put("scope","actual production core on host JVM; source-frame device test not run").put("cases",rows).put("ordinary_and_scoped_admission",true).put("mixed_safe_unit_retained",true).toString(2))
  println("Passed ${cases.length()} source boundary fixtures and core admission regressions")
 }
}
