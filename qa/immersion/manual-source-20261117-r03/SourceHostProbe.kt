package co.fallsoft.vipi
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import java.io.File
object SourceHostProbe {
 @JvmStatic fun main(args:Array<String>)=runBlocking {
  val reverse=LookupFirst.resolve(LookupFirstRequest("Hola, amiga.","en","es",allowModelTranslation=false),{true},reference={_,a,_->if(a=="es")"Hello, friend." else null},identify={error("authored direction")},modelsReady={error("no model")},translate={_,_,_->error("no model")},align={a,b,_->ImmersionResult(a,b,emptyList())})
  check(reverse.result!!.original=="Hello, friend."&&reverse.result!!.translation=="Hola, amiga.")
  check(reverse.resolvedInputLanguage=="es"&&reverse.cachedInvocation().resolvedInputLanguage=="es")
  val miss=LookupFirst.resolve(LookupFirstRequest("Una frase desconocida.","en","es",allowModelTranslation=false),{true},reference={_,_,_->null},identify={"es"},modelsReady={error("no model")},translate={_,_,_->error("no model")},align={_,_,_->error("no alignment")})
  check(miss.status==ImmersionStatus.NO_LOCAL_MATCH&&miss.result==null&&miss.resolvedInputLanguage=="es")
  var valid=true
  val stale=LookupFirst.resolve(LookupFirstRequest("Una frase.","en","es","es"),{valid},reference={_,_,_->null},identify={null},modelsReady={valid=false;false},translate={_,_,_->"x"},align={a,b,_->ImmersionResult(a,b,emptyList())})
  check(stale.status==ImmersionStatus.STALE&&stale.resolvedInputLanguage==null)
  val invalid=LookupFirst.resolve(LookupFirstRequest("x","en","es","fr"),{true},reference={_,_,_->error("invalid before callback")},identify={null},modelsReady={false},translate={_,_,_->"x"},align={a,b,_->ImmersionResult(a,b,emptyList())})
  check(invalid.resolvedInputLanguage==null)
  val raw="Hola, amiga."
  val mismatch=ManualSourceCoordinates.resolve(raw,reverse.result!!.original,7,13)!!
  check(mismatch==ManualSourceRange(0,raw.length,true))
  check(ManualSourceCoordinates.resolve(raw,raw,6,11)==ManualSourceRange(6,11,false))
  val nfd="cafe\u0301"
  check(ManualSourceCoordinates.resolve(nfd,"café",0,4)!!.expanded)
  for((text,a,b) in listOf(Triple("A😀B",2,3),Triple(nfd,0,4),Triple("Hola.",-1,2),Triple("Hola.",0,99)))check(ManualSourceCoordinates.resolve(text,text,a,b)==ManualSourceRange(0,text.length,true))
  check(ManualSourceCoordinates.resolve("","Hello",0,5)==null)
  val request=ManualTranslationRequest("reverse",raw,mismatch.startUTF16,mismatch.endUTF16,"en","es",reverse.resolvedInputLanguage,1,1)
  var actualInput="";var direction=""
  val translated=ManualTranslationResolver.resolve(request,{true},reference={_,_,_->null},identify={error("direction retained")},modelsReady={_,_->true},translate={text,a,b->actualInput=text;direction="$a-$b";"Hello, friend."},reading={_,_->null})
  check(translated.status==ManualTranslationStatus.READY&&actualInput==raw&&direction=="es-en")
  File(args[0]).writeText(JSONObject().put("passed",true).put("scope","host JVM production core/helper with injected translation; not mobile UI or model quality").put("checks",10).toString(2))
  println("Passed source-coordinate and actual-language regressions")
 }
}
