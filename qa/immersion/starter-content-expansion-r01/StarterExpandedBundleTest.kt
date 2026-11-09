package co.fallsoft.vipi
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File
class StarterExpandedBundleTest {
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No preparation")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation")
  override fun close() {}
 }
 @Test fun finalBundledDefaultRoute()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiExpandedBundle")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val observations=JSONArray()
  val controls=listOf(
   Triple("A school of fish swam past us.","school",null),Triple("Schools of fish swim near the beach.","Schools","beach"),
   Triple("The schools have a garden.","schools","garden"),Triple("The school has a garden.","school","garden"),
   Triple("Apple announced a new phone.","Apple",null),Triple("apple announced a new phone.","apple",null),
   Triple("Jobs changed personal computing.","Jobs",null),Triple("jobs changed personal computing.","jobs",null),
   Triple("I cut an apple for lunch.","apple","lunch"),Triple("There are jobs near my house.","jobs","house"),
   Triple("I found a job near my house.",null,"job"),Triple("Send coffee_today.txt and enjoy music.","coffee_today.txt","music"),
   Triple("The coffee and bread are for lunch.",null,"lunch"))
  for(target in listOf("ja","sw")) {
   val expected=if(target=="ja") "26d499d87e12fbf6bb938fcbb095d084f2f09ef301ca2b60a9a0dc42b10480d0" else "e474bfebae95e6f8a6f58c1eeaaf6be65582fad243ae33a6a83e9e1e1f785373"
   val manifest=JSONObject(context.assets.open("immersion/"+if(target=="ja") "starter-catalog.json" else "starter-sw-catalog.json").bufferedReader().use{it.readText()})
   val bytes=context.assets.open("immersion/"+manifest.getString("file")).use{it.readBytes()};assertEquals(expected,JapaneseStarterLookup.sha(bytes));assertEquals(if(target=="ja")189 else 213,manifest.getInt("entries"))
   val provider=requireNotNull(if(target=="ja") JapaneseStarterLookup.bundledIfPromoted(context) else SwahiliStarterLookup.bundledIfPromoted(context));assertTrue(provider.cacheIdentity.contains(expected));assertTrue(provider.cacheIdentity.endsWith(":packing-1"))
   val engine=ConversationImmersion(context,"en",target,.75,translator=NoTranslation(),qaModelsReady=false)
   try { for((index,c) in controls.withIndex()) {
    val(text,untouched,required)=c;val id="expanded-$target-$index";engine.selectInputLanguage(id,"en");val value=engine.presentation(text,"en",id);val spans=value?.spans ?: emptyList();assertEquals(0,requireNotNull(engine.lastOutcome).localTranslationCalls)
    if(untouched!=null){val a=text.indexOf(untouched);assertTrue(a>=0);assertFalse(spans.any{it.start<a+untouched.length && a<it.end})}
    if(required!=null){val a=text.lastIndexOf(required);assertTrue(spans.any{it.start==a && it.end==a+required.length})}
    val mixed=if(value==null)text else ImmersionText.project(value)
    if(index==controls.lastIndex)assertEquals(if(target=="ja")"The kōhī and pan are for chuushoku." else "The kahawa na mkate are for chakula cha mchana.",mixed)
    observations.put(JSONObject().put("pair","en-$target").put("source",text).put("mixed",mixed).put("bundle_sha256",expected).put("origin",engine.lastOutcome?.origin?.name).put("translation_calls",0).put("spans",JSONArray(spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: JSONObject.NULL).put("scope",JSONArray(listOf(it.start,it.end)))})))
   }} finally {engine.close()}
  }
  assertEquals(26,observations.length());File(context.filesDir,"expanded-bundle-default-route.json").writeText(observations.toString())
 }
}
