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
class StarterRouteQualificationActivity:ComponentActivity() {
    private class NoTranslation:LanguageTranslation {
        override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model preparation")
        override suspend fun translate(text:String,source:String,target:String):String=error("No translation permitted")
        override fun close() {}
    }
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val target=requireNotNull(intent.getStringExtra("target"));require(target in setOf("ja","sw"))
        val expanded=intent.getBooleanExtra("expanded",false)
        val packed=intent.getBooleanExtra("packed",false) || expanded
        val original=if(expanded) "The coffee and bread are for lunch." else if(packed) "My family and my family enjoy pizza." else "Country music is fun!"
        val density=if(packed) .75 else .25
        val expected=if(expanded) { if(target=="ja") listOf("コーヒー","パン","昼食") else listOf("kahawa","na","mkate","chakula cha mchana") } else if(packed) { if(target=="ja") listOf("家族","家族","ピザ") else listOf("familia","na","familia","piza") } else listOf(if(target=="ja") "音楽" else "muziki")
        val face=expected.joinToString(" ")
        val out=File(filesDir,"starter-route-ui-${if(expanded) "expanded-" else if(packed) "packed-" else ""}$target").apply{mkdirs()}
        setContent { VipiTheme(Appearance.LIGHT) {
            val scope=rememberCoroutineScope()
            val owner=remember { ConversationImmersion(this,"en",target,density,translator=NoTranslation(),qaModelsReady=false) }
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
                val proof=JSONObject().put("original",original).put("target",target).put("density",density).put("packed",packed).put("known_ids",JSONArray())
                    .put("provider_identity",BundledStarterLookup.provider(this@StarterRouteQualificationActivity)?.cacheIdentity).put("origin",outcome.origin?.name)
                    .put("spans",JSONArray(result.spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: JSONObject.NULL).put("scope",JSONArray(listOf(it.start,it.end)))}))
                    .put("speech_segments",JSONArray(result.speech("en",target).map{JSONObject().put("text",it.text).put("language",it.language)}))
                    .put("translation_calls",outcome.localTranslationCalls)
                File(out,"proof.json").writeText(proof.toString())
                withContext(Dispatchers.Main.immediate) { speech.prepare(mapOf("en" to "Hello.",target to face));ready=true }
            }
            Column(Modifier.padding(20.dp)) {
                Text("Default source-first chat connection QA")
                if(ready) ConversationImmersionText(original,"starter-ui-$target",owner,speech,false,{},metadata={Text("Owned local message")})
                Text(speech.state.name)
            }
        } }
    }
}
