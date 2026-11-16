package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

class AdditiveExposureDeviceTest {
 @Test fun sharedPolicyFixtures() {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val root=JSONObject(File(inst.targetContext.filesDir,"additive-selection-r01/fixtures.json").readText());val cases=root.getJSONArray("cases")
  for(i in 0 until cases.length()) {
   val c=cases.getJSONObject(i);val arr=c.getJSONArray("candidates");val states=mutableMapOf<String,AdditiveExposureSelection.Seen>();val units=mutableListOf<SourceReferenceUnit>()
   for(j in 0 until arr.length()) {val x=arr.getJSONObject(j);if(!x.getBoolean("eligible"))continue;val id=x.getString("id");states[id]=AdditiveExposureSelection.Seen(x.getString("state")=="seen",x.getBoolean("due"));units+=SourceReferenceUnit(x.getInt("start"),x.getInt("end"),id,"target",null,id,"a".repeat(64),x.optInt("cost",1),selectionPriority=if(x.has("priority")) x.getInt("priority") else null)}
   val chosen=AdditiveExposureSelection.selectWithBudgets(units,c.getInt("novel_budget"),c.getInt("hard_ceiling")){states.getValue(it.referenceId)}.map{it.referenceId}
   val exp=c.getJSONArray("expected");assertEquals(c.getString("id"),(0 until exp.length()).map{exp.getString(it)},chosen)
  }
 }
 @Test fun actualSourceRouteUsesOnlyDisplayedFrameHistory() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true");val context=inst.targetContext;val account=UUID.randomUUID();val vault=MessageVault(context,account);val store=VocabularyFamiliarityStore(vault)
  val text="The train and bank are near the house.";val words=listOf("train" to "tren","bank" to "banco","house" to "casa")
  val units=words.mapIndexed { i,(src,tgt)->val a=text.indexOf(src);SourceReferenceUnit(a,a+src.length,src,tgt,null,"frame:${"a".repeat(64)}:test-$i","a".repeat(64),1,"output-$i",ApprovedLearningIdentity("test-$i","synthetic meaning $i","")) }
  val waiting=CompletableDeferred<Unit>();val release=CompletableDeferred<Unit>()
  val provider=object:SourceLookupProvider {
   override val cacheIdentity="additive-test-v1"
   override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
    if(original.endsWith("Today.")){waiting.complete(Unit);release.await()}
    val partial=SourceReferencePresentation.create(original,target,units,density,if(original==text)8 else 9)
    return SourceLookupEvidence(original,source,target,cacheIdentity,partial,emptyList(),units,if(original==text)8 else 9)
   }
  }
  val owner=ConversationImmersion(context,"en","es",.25,sourceLookup=provider,familiarity=store,qaModelsReady=false)
  try {
   val first=requireNotNull(owner.presentation(text,"en")) { "first outcome: ${owner.lastOutcome}" } as PartialImmersionResult;assertEquals(2,first.spans.size)
   val pending=async { owner.presentation(text+" Today.","en") };withTimeout(10_000){waiting.await()}
   val exposed=first.spans.first();owner.observeExposure(first,listOf(exposed.copy(translated="wrong")))
   assertFalse(store.sourceSeen(first.references.first(),"en","es",(System.currentTimeMillis()/86400000L).toInt()).observed)
   owner.observeExposure(first,listOf(exposed));release.complete(Unit)
   val inflight=requireNotNull(withTimeout(10_000){pending.await()});assertEquals(3,inflight.spans.size)
   assertTrue(store.sourceSeen(first.references.first(),"en","es",(System.currentTimeMillis()/86400000L).toInt()).observed)
   val next=requireNotNull(owner.presentation(text+" Tomorrow.","en"));assertEquals(3,next.spans.size)
   assertEquals(2,first.spans.size) // immutable visible snapshot does not reshuffle
   assertFalse(store.sourceSeen(first.references.first(),"en","fr",(System.currentTimeMillis()/86400000L).toInt()).observed)
  } finally {owner.close();vault.close();vault.file.parentFile!!.deleteRecursively();KeyStore.getInstance("AndroidKeyStore").apply{load(null)}.deleteEntry("co.fallsoft.vipi.messages.$account")}
 }
 @Test fun reviewedFrameIdentityIsScopedAndClockSafe() {
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val account=UUID.randomUUID();val vault=MessageVault(context,account);val store=VocabularyFamiliarityStore(vault)
  val reference="frame:${"a".repeat(64)}:bank-financial";val financial=SourceReferenceUnit(0,4,"bank","banque",null,reference,"a".repeat(64),1,learningIdentity=ApprovedLearningIdentity("bank-financial","financial institution",""))
  val otherContext=financial.copy(start=8,end=12);val river=financial.copy(referenceId="frame:${"a".repeat(64)}:bank-river",translated="rive",learningIdentity=ApprovedLearningIdentity("bank-river","river bank",""));val newPack=financial.copy(referenceId="frame:${"b".repeat(64)}:bank-financial",catalogSha256="b".repeat(64))
  try {
   assertTrue(store.observeSourceUnits(listOf(financial),"en","fr",100));assertFalse(store.observeSourceUnits(listOf(financial),"en","fr",100));assertFalse(store.observeSourceUnits(listOf(financial),"en","fr",99))
   assertTrue(store.sourceSeen(otherContext,"en","fr",101).observed);assertTrue(store.sourceSeen(otherContext,"en","fr",101).due)
   assertTrue(store.observeSourceUnits(listOf(financial),"en","fr",101));assertFalse(store.sourceSeen(otherContext,"en","fr",102).due);assertTrue(store.sourceSeen(otherContext,"en","fr",103).due)
   assertFalse(store.observeSourceUnits(listOf(financial.copy(learningIdentity=null)),"en","fr",101));assertFalse(store.observeSourceUnits(listOf(financial.copy(referenceId="frame:wrong:bank-financial")),"en","fr",101));assertFalse(store.sourceSeen(river,"en","fr",101).observed);assertTrue(store.sourceSeen(newPack,"en","fr",101).observed);assertFalse(store.sourceSeen(financial.copy(learningIdentity=ApprovedLearningIdentity("bank-financial","changed meaning","")),"en","fr",101).observed);assertFalse(store.sourceSeen(financial.copy(translated="caisse"),"en","fr",101).observed);assertFalse(store.sourceSeen(financial,"en","es",101).observed)
   vault.transaction { val ids=vault.ids("immersion-frame-exposure-next");assertEquals(1,ids.size);assertEquals(64,ids.single().length);assertFalse(ids.single().contains("bank"));val payload=JSONObject(requireNotNull(vault.get("immersion-frame-exposure-next",ids.single())).toString(Charsets.UTF_8));assertEquals(101,payload.getInt("lastDay"));assertEquals(2,payload.getInt("exposureDays"));assertEquals(setOf("lastDay","exposureDays"),payload.keys().asSequence().toSet()) }
   // Apple-compatible JSON is decoded in the same account-local encrypted namespace.
   val apple=financial.copy(referenceId="frame:${"a".repeat(64)}:apple-pattern",learningIdentity=ApprovedLearningIdentity("apple-pattern","apple-compatible",""))
   val secret=vault.transaction{requireNotNull(vault.get("immersion-metadata","id-key-v1"))};val payload=encodeFrameIdentity(listOf("v2-frame-sense-1","en","fr","apple-pattern","bank","banque","apple-compatible",""));val id=javax.crypto.Mac.getInstance("HmacSHA256").apply{init(javax.crypto.spec.SecretKeySpec(secret,"HmacSHA256"))}.doFinal(payload).joinToString(""){"%02x".format(it)}
   vault.transaction {vault.put("immersion-frame-exposure-next",id,"{\"exposureDays\":3,\"lastDay\":200}".toByteArray())};assertTrue(store.sourceSeen(apple,"en","fr",204).due)
  } finally {vault.close();vault.file.parentFile!!.deleteRecursively();KeyStore.getInstance("AndroidKeyStore").apply{load(null)}.deleteEntry("co.fallsoft.vipi.messages.$account")}
 }
 @Test fun sharedIdentityVectors() {
  val inst=InstrumentationRegistry.getInstrumentation();val root=JSONObject(File(inst.targetContext.filesDir,"additive-selection-r01/identity-fixtures.json").readText());val key=root.getString("test_key_hex").chunked(2).map{it.toInt(16).toByte()}.toByteArray();val cases=root.getJSONArray("cases")
  fun hex(b:ByteArray)=b.joinToString(""){"%02x".format(it)}
  for(i in 0 until cases.length()) {val c=cases.getJSONObject(i);if(!c.getBoolean("verified_reviewed_pattern"))continue;val f=c.getJSONObject("fields");val fields=listOf("version","source_language","target_language","pattern_id","source_face","target_face","meaning","reading").map{f.getString(it)};val bytes=encodeFrameIdentity(fields);assertEquals(c.getString("id"),c.getString("expected_encoded_hex"),hex(bytes));val mac=javax.crypto.Mac.getInstance("HmacSHA256").apply{init(javax.crypto.spec.SecretKeySpec(key,"HmacSHA256"))};assertEquals(c.getString("id"),c.getString("expected_hmac_sha256"),hex(mac.doFinal(bytes))) }
 }
 @Test fun lateSeenFrameRemainsInApprovedPool() {
  val text="one two three four five six seven eight";val sources=listOf("one","two","three","four","five","six","seven");val targets=listOf("uno","dos","tres","cuatro","cinco","seis","siete");val patterns=org.json.JSONArray()
  for(i in sources.indices) {val word=sources[i];val v=JSONObject().put("context",word).put("focus_utf16",org.json.JSONArray(listOf(0,word.length)));patterns.put(JSONObject().put("id","pool-$i").put("source_only_permission",true).put("pair","en-es").put("source",word).put("target",targets[i]).put("meaning","number $i").put("concept_id","number-$i").put("reading","").put("variants",org.json.JSONArray().put(v)))}
  val pack=JSONObject().put("schema","vipi-source-frame-pack-1").put("source","en").put("target","es").put("policy","reference-first-source-frames-1").put("approval_sha256","0".repeat(64)).put("version","test").put("patterns",patterns);val bytes=pack.toString().toByteArray();val manifest=JSONObject().put("schema","vipi-source-frame-manifest-1").put("source","en").put("target","es").put("policy","reference-first-source-frames-1").put("file","source-frames-en-es-001.json").put("version","test").put("sha256",JapaneseStarterLookup.sha(bytes)).put("bytes",bytes.size).put("patterns",patterns.length())
  val frame=SourceFrameLookup(bytes,manifest.toString().toByteArray(),"es","empty","en");val result=frame.resolve(text,.75,emptySet(),SourceLookupEvidence(text,"en","es","empty",null,emptyList()),emptyList());assertEquals(7,result.candidatePool.size);assertEquals(6,requireNotNull(result.partial).spans.size)
  val selected=AdditiveExposureSelection.select(result.candidatePool,8,.25){AdditiveExposureSelection.Seen(it.original=="seven",it.original=="seven")};assertEquals(3,selected.size);assertEquals("seven",selected.last().original);assertEquals(result.candidatePool.filter{it.original!="seven"}.take(2).map{it.original}.toSet(),selected.filter{it.original!="seven"}.map{it.original}.toSet());val presentation=requireNotNull(SourceReferencePresentation.create(text,"es",selected,.75,8));assertEquals(selected.map{it.original},presentation.spans.map{it.original})
 }
 @Test fun sourcePoolKeepsStrongestNestedCandidate() {
  fun unit(a:Int,b:Int,id:String)=SourceReferenceUnit(a,b,id,"target",null,id,"a".repeat(64),1)
  val phrase=unit(0,9,"strong-phrase");val nested=unit(0,4,"weak-word");val later=unit(10,15,"late-seen")
  assertEquals(listOf(phrase,later),resolveSourceCandidateOverlaps(listOf(phrase,nested,later)))
 }
 @Test fun actualBundledCatalogPassesFullPoolAndPreservesMasks() = runBlocking {
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val provider=requireNotNull(BundledStarterLookup.provider(context));val text="passport airport suitcase bicycle fridge dishwasher toothpaste today"
  val evidence=provider.lookup(text,"en","es",.75);assertTrue(evidence.isValid(text,"en","es",provider.cacheIdentity));assertTrue("actual bundled pool must include late candidates",evidence.candidatePool.size>=7)
  val late=evidence.candidatePool.maxBy{it.start};val selected=AdditiveExposureSelection.select(evidence.candidatePool,8,.25){AdditiveExposureSelection.Seen(it==late,it==late)};assertEquals(3,selected.size);assertTrue(selected.contains(late))
  val literal="https://example.com/passport";val masked=provider.lookup(literal,"en","es",.75);assertTrue(masked.candidatePool.none{it.original=="passport"})
  val nested="phone charger";val overlap=provider.lookup(nested,"en","es",.75);assertTrue(overlap.candidatePool.none{a->overlap.candidatePool.any{b->a!==b && a.start<b.end && b.start<a.end}})
 }
 @Test fun novelSelectionRespectsApprovedProducerPriority() {
  val early=SourceReferenceUnit(0,1,"I","yo",null,"function","a".repeat(64),1,selectionPriority=1)
  val later=SourceReferenceUnit(2,7,"music","música",null,"content","a".repeat(64),1,selectionPriority=0)
  assertEquals(listOf(later),AdditiveExposureSelection.selectWithBudgets(listOf(early,later),1,1){AdditiveExposureSelection.Seen(false)})
 }
 @Test fun dedicatedStarterPoolTrace() = runBlocking {
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val provider=requireNotNull(BundledStarterLookup.provider(context));val rows=org.json.JSONArray()
  for(target in listOf("ja","sw")) for(text in listOf("I heard music.","I like music.")) {
   val evidence=provider.lookup(text,"en",target,.75);assertTrue(evidence.isValid(text,"en",target,provider.cacheIdentity));val words=LocalImmersion.words(text,"en").size
   val selected=AdditiveExposureSelection.select(evidence.candidatePool,words,.25){AdditiveExposureSelection.Seen(false)}
   val pool=evidence.candidatePool.map{it.original};if("I" in pool && "music" in pool)assertEquals("music",selected.firstOrNull()?.original)
   rows.put(JSONObject().put("target",target).put("text",text).put("provider_identity",provider.cacheIdentity).put("pool",org.json.JSONArray(evidence.candidatePool.map{JSONObject().put("source",it.original).put("priority",it.selectionPriority?:JSONObject.NULL).put("reference",it.referenceId)})).put("selected",org.json.JSONArray(selected.map{it.original})).put("baseline_partial",org.json.JSONArray(evidence.partial?.spans.orEmpty().map{it.original})))
  }
  File(context.filesDir,"additive-selection-r01/starter-trace.json").writeText(rows.toString(2))
 }
}
