package co.fallsoft.vipi
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONArray
import java.io.File

/** DEBUG-only original-message host, with the actual Android activity/lifecycle/clock. */
class FrameRouteQualificationActivity:ComponentActivity() {
    private class NoTranslation:LanguageTranslation {
        override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model preparation")
        override suspend fun translate(text:String,source:String,target:String):String=error("No translation permitted")
        override fun close() {}
    }
    private var routingBranch="not_invoked"
    private fun createProvider(target:String):SourceLookupProvider {
        fun read(name:String)=File(filesDir,name).readBytes()
        val manifestBytes=read("manifest.json")
        check(JapaneseStarterLookup.sha(manifestBytes)=="7ebbcfdb1e72290a5fdd1beda5c9c99c1fda1940a92fc1152876e89880cc7896")
        val manifest=JSONObject(manifestBytes.toString(Charsets.UTF_8));val files=manifest.getJSONObject("files")
        for(name in files.keys())check(JapaneseStarterLookup.sha(read(name))==files.getString(name))
        val spec=manifest.getJSONObject("packs").getJSONObject(target)
        val baseline:SourceLookupProvider;val raw:()->List<FrameStarterCandidate>
        if(target=="ja") {
            val x=JapaneseStarterLookup(read(spec.getString("pack")),read(spec.getString("manifest")),emptySet(),true)
            baseline=x;raw={x.rawCandidates}
        } else {
            val x=SwahiliStarterLookup(read(spec.getString("pack")),read(spec.getString("manifest")),emptySet(),true)
            baseline=x;raw={x.rawCandidates}
        }
        val adapter=FrameContextAdapter(read(spec.getString("patterns")),read("permission-proposal.json"),target,baseline.cacheIdentity)
        val identity=adapter.identity+":reference-first-v1";val catalog=BundledImmersionCatalog(this);val expectedTarget=target
        return object:SourceLookupProvider {
            override val cacheIdentity=identity
            override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
                require(source=="en" && target==expectedTarget)
                val b=baseline.lookup(original,source,target,density)
                val reference=catalog.reference(original,source,target)
                routingBranch=if(reference!=null)"existing_forward_reference_baseline_evidence" else "reference_miss_frame_evidence"
                val value=if(reference!=null)b else adapter.resolve(original,density,emptySet(),b,raw())
                return SourceLookupEvidence(value.original,value.source,value.target,identity,value.partial,value.recognitions)
            }
        }
    }
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val target=requireNotNull(intent.getStringExtra("target"));require(target in setOf("ja","sw"))
        val original="We need a phone charger and your phone number."
        val density=.75
        val expected=if(target=="ja")listOf("私たち","携帯電話の充電器","電話番号") else listOf("sisi","chaja ya simu","na","Nambari ya simu")
        val reviewedProvider=createProvider(target)
        val face=expected.joinToString(" ")
        val out=File(filesDir,"frame-route-ui-$target").apply{mkdirs()}
        setContent { VipiTheme(Appearance.LIGHT) {
            val scope=rememberCoroutineScope()
            val owner=remember { ConversationImmersion(this,"en",target,density,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=emptySet(),sourceLookup=reviewedProvider) }
            val speech=remember { SpeechPlayback(this,"en",target,scope) }
            val events=remember { mutableListOf<String>() };val speechState=speech.state.name
            var ready by remember { mutableStateOf(false) }
            SideEffect {
                if(events.lastOrNull()!=speechState) {
                    events.add(speechState)
                    File(out,"speech-events.json").writeText(JSONObject().put("states",JSONArray(events)).put("error",speech.error ?: JSONObject.NULL).toString())
                }
            }
            DisposableEffect(Unit) { onDispose { owner.close();speech.close() } }
            LaunchedEffect(Unit) {
                owner.selectInputLanguage("starter-ui-$target","en")
                val result=requireNotNull(owner.presentation(original,"en","starter-ui-$target"));val outcome=requireNotNull(owner.lastOutcome)
                check(outcome.origin?.name=="SOURCE_REFERENCE_PARTIAL" && outcome.localTranslationCalls==0)
                check(result.spans.map{it.translated}==expected)
                val proof=JSONObject().put("original",original).put("target",target).put("density",density).put("test_only_reference_first_provider",true).put("known_ids",JSONArray())
                    .put("provider_identity",reviewedProvider.cacheIdentity).put("origin",outcome.origin?.name)
                    .put("spans",JSONArray(result.spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: JSONObject.NULL).put("scope",JSONArray(listOf(it.start,it.end)))}))
                    .put("speech_segments",JSONArray(result.speech("en",target).map{JSONObject().put("text",it.text).put("language",it.language)}))
                    .put("translation_calls",outcome.localTranslationCalls).put("routing_branch",routingBranch).put("supplied_target_or_span",false)
                File(out,"proof.json").writeText(proof.toString())
                withContext(Dispatchers.Main.immediate) { speech.prepare(mapOf("en" to "Hello.",target to face));ready=true }
            }
            Column(Modifier.padding(20.dp)) {
                Text("Private source-context chat connection QA")
                if(ready) ConversationImmersionText(original,"starter-ui-$target",owner,speech,false,{},metadata={Text("Owned local message")})
                Text(speech.state.name)
            }
        } }
    }
}
