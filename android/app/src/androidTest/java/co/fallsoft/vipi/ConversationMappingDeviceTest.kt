package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ContextMapping
import co.fallsoft.vipi.core.ContextMappingMatcher
import co.fallsoft.vipi.core.ContextPart
import co.fallsoft.vipi.core.VocabularyTargetForm
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** Native mapping and reading qualification against retained real local output. */
@RunWith(AndroidJUnit4::class)
class ConversationMappingDeviceTest {
    @Test fun recordExpandedContextMappings() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val args=InstrumentationRegistry.getArguments()
        val run=args.getString("vipiRunID") ?: "003"
        val revision=args.getString("vipiReceiptID") ?: run
        require(run.matches(Regex("[0-9]{3}")))
        require(revision.matches(Regex("[0-9]{3}")))
        val input=File(context.filesDir,"phrase-observations-$run.json").readBytes()
        val capture=JSONObject(input.toString(Charsets.UTF_8))
        assertTrue(capture.getBoolean("complete"))
        val referenceBytes=File(context.filesDir,"immersion-qa/conversation-records.jsonl").readBytes()
        val references=referenceBytes.toString(Charsets.UTF_8).lineSequence().filter { it.isNotBlank() }
            .map(::JSONObject).associateBy { it.getString("logical_id") }
        val rows=capture.getJSONArray("results");val output=JSONArray();var accepted=0
        repeat(rows.length()) { index ->
            val row=rows.getJSONObject(index)
            val original=row.getString("original");val translation=row.getString("translation")
            val source=row.getString("source");val target=row.getString("target")
            val start=row.getInt("start");val end=row.getInt("end")
            val word=row.getString("source_word");val translated=row.getString("expected_target")
            val reading=row.getString("expected_reading")
            assertEquals(word,original.substring(start,end))
            val reference=requireNotNull(references[row.getString("case")])
            assertEquals(original,reference.getString("source_context"))
            assertEquals(translated,reference.getString("target"));assertEquals(reading,reference.getString("reading"))
            val targetContext=reference.getString("target_context");val focus=reference.getJSONArray("target_span")
            val ts=targetContext.offsetByCodePoints(0,focus.getInt(0));val te=targetContext.offsetByCodePoints(0,focus.getInt(1))
            assertEquals(translated,targetContext.substring(ts,te))
            val touching=LocalImmersion.words(targetContext,target).filter { it.first<te && it.last>=ts }
            val forms=if(touching.isEmpty())emptyList() else {
                val a=minOf(ts,touching.first().first);val b=maxOf(te,touching.last().last+1)
                listOf(VocabularyTargetForm(targetContext.substring(a,b),translated,ts-a,te-a))
            }
            val parts=buildList {
                if(start>0)add(ContextPart.Literal(original.substring(0,start)))
                add(ContextPart.Focus(word))
                if(end<original.length)add(ContextPart.Literal(original.substring(end)))
            }
            val mapping=ContextMapping(row.getString("case"),row.getString("concept"),source,target,parts,
                listOf(translated),if(reading.isEmpty())emptyMap() else mapOf(translated to listOf(reading)),forms)
            val entries=ContextMappingMatcher.entries(original,source,target,listOf(mapping))
            assertEquals(1,entries.size)
            val result=LocalImmersion.align(original,translation,entries,1.0,source,target)
            val spans=JSONArray()
            for(span in result.spans) {
                assertEquals(start,span.start);assertEquals(end,span.end)
                assertEquals(word,span.original)
                if(target in setOf("ar","zh","ja","ko"))assertFalse(span.romanization.isNullOrBlank())
                spans.put(JSONObject().put("start",span.start).put("end",span.end).put("target",span.translated)
                    .put("reading",span.romanization ?: JSONObject.NULL))
            }
            if(result.spans.isNotEmpty())accepted++
            output.put(JSONObject().put("case",row.getString("case")).put("source",source).put("target",target)
                .put("original",original).put("translation",translation).put("spans",spans)
                .put("visible_script",result.speech(source,target).joinToString(""){it.text}))
        }
        val receipt=File(context.filesDir,"conversation-mappings-$revision.json")
        check(!receipt.exists())
        receipt.writeText(JSONObject().put("schema","vipi-native-conversation-mappings-1")
            .put("capture_sha256",MessageDigest.getInstance("SHA-256").digest(input).joinToString(""){"%02x".format(it)})
            .put("reference_sha256",MessageDigest.getInstance("SHA-256").digest(referenceBytes).joinToString(""){"%02x".format(it)})
            .put("cases",rows.length()).put("cases_with_immersion",accepted).put("platform","Android")
            .put("scope","authored development contexts against retained actual ML Kit output")
            .put("independent_linguistic_acceptance",false).put("general_chat_integration",false)
            .put("results",output).toString(2))
    }
}
