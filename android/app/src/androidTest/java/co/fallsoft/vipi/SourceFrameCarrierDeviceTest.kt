package co.fallsoft.vipi

import co.fallsoft.vipi.core.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SourceFrameCarrierDeviceTest {
 private fun variant(context:String,start:Int,end:Int,rule:String)=JSONObject().put("context",context)
  .put("focus_utf16",JSONArray(listOf(start,end))).put("carrier_utf16",JSONArray(listOf(0,context.length))).put("carrier_rule",rule)
 private fun frame(source:String,head:String,variant:JSONObject):SourceFrameLookup {
  val pattern=JSONObject().put("id","carrier-test").put("source_only_permission",true).put("pair","$source-en")
   .put("source",head).put("target",if(source=="ar")"water" else "book").put("meaning","synthetic guarded noun")
   .put("concept_id","noun").put("reading","").put("variants",JSONArray().put(variant))
  val pack=JSONObject().put("schema","vipi-source-frame-pack-1").put("source",source).put("target","en")
   .put("policy","reference-first-source-frames-1").put("approval_sha256","0".repeat(64)).put("version","test").put("patterns",JSONArray().put(pattern))
  val bytes=pack.toString().toByteArray()
  val manifest=JSONObject().put("schema","vipi-source-frame-manifest-1").put("source",source).put("target","en")
   .put("policy","reference-first-source-frames-1").put("file","source-frames-$source-en-001.json").put("version","test")
   .put("sha256",JapaneseStarterLookup.sha(bytes)).put("bytes",bytes.size).put("patterns",1)
  return SourceFrameLookup(bytes,manifest.toString().toByteArray(),"en","empty",source)
 }
 private fun result(frame:SourceFrameLookup,source:String,text:String,known:Set<String> = emptySet()) =
  frame.resolve(text,.5,known,SourceLookupEvidence(text,source,"en","empty",null,emptyList()),emptyList())
 @Test fun exactCarriersPreserveGrammarAndRejectLargerTokens() {
  for((source,head,v) in listOf(Triple("ko","책",variant("책을",0,1,"hangul-noun-particles-1")))) {
   val f=frame(source,head,v);val text=v.getString("context")
   val p=requireNotNull(result(f,source,text).partial)
   assertEquals(head,p.spans.single().original)
   assertEquals(if(source=="ar")"الwater" else "book을",ImmersionText.project(p,showScript=true))
   assertNull(result(f,source,(if(source=="ar")"ب" else "집")+text).partial)
   assertNull(result(f,source,text+(if(source=="ar")"ك" else "집")).partial)
   assertNull(result(f,source,"https://example.com/$text").partial)
   assertNull(result(f,source,text,setOf("noun")).partial)
   val noCarrier=JSONObject(v.toString()).apply{remove("carrier_utf16");remove("carrier_rule")}
   assertNull(result(frame(source,head,noCarrier),source,text).partial)
  }
 }
 @Test fun reviewedArabicCarrierCannotSplitJoinedOrthography() {
  for((word,head) in listOf("الماء" to "ماء","الموسيقى" to "موسيقى")) {
   val v=variant(word,2,word.length,"supplied-singular-definite-article-1")
   val f=frame("ar",head,v)
   assertNull(result(f,"ar",word).partial)
   assertEquals("partial_arabic_word",f.geometry(word).getJSONObject(0).getString("reason"))
  }
 }
 @Test fun malformedUnlicensedAndWrongAllomorphCarriersFailClosed() {
  val variants=listOf(
   variant("책를",0,1,"hangul-noun-particles-1"),
   variant("책을",0,1,"unknown"),
   variant("책을",0,1,"hangul-noun-particles-1").apply{remove("carrier_rule")},
   variant("책을",0,1,"hangul-noun-particles-1").put("carrier_utf16",JSONArray(listOf(-1,2))),
   variant("책을만",0,1,"hangul-noun-particles-1"))
  for(v in variants)assertTrue(runCatching{frame("ko","책",v)}.isFailure)
  assertTrue(runCatching{frame("ar","كتاب",variant("كتابي",0,4,"supplied-singular-definite-article-1"))}.isFailure)
 }
}
