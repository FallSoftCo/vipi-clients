package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.TranslationIntegrity
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** Broad public dictionary replay; availability is not semantic accuracy. */
@RunWith(AndroidJUnit4::class)
class LexicalCoverageDeviceTest {
    @Test fun publishedDictionaryConcordanceAndConversationReplay() {
        val args=InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator")=="true")
        val revision=requireNotNull(args.getString("vipiLexicalRun"));require(revision.matches(Regex("[0-9]{3}")))
        val fixture=args.getString("vipiLexicalFixture") ?: revision;require(fixture.matches(Regex("[0-9]{3}")))
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val root=File(context.filesDir,"lexical-qualification-$fixture")
        val manifest=JSONObject(File(root,"manifest.json").readText())
        check(manifest.getString("schema")=="vipi-lexical-qualification-1")
        fun sha(file:File):String {
            val digest=MessageDigest.getInstance("SHA-256")
            file.inputStream().use { stream -> val buffer=ByteArray(65536);var count=stream.read(buffer)
                while(count>=0) {digest.update(buffer,0,count);count=stream.read(buffer)} }
            return digest.digest().joinToString(""){"%02x".format(it)}
        }
        val databases=mutableMapOf<String,SQLiteDatabase>()
        var witnessDB:SQLiteDatabase?=null
        val output=File(context.filesDir,"lexical-coverage-$revision.json");check(!output.exists())
        val failures=JSONArray();val report=JSONObject().put("schema","vipi-lexical-coverage-1")
            .put("run",revision).put("fixture",fixture).put("manifest_sha256",sha(File(root,"manifest.json"))).put("platform","android")
            .put("translation_reused",true).put("classification_exercised",false)
            .put("independent_semantic_acceptance",false).put("report_storage","streamed-jsonl")
        val journal=File(context.filesDir,"lexical-coverage-$revision.outcomes.jsonl");check(!journal.exists())
        val journalWriter=journal.bufferedWriter()
        var completedCases=0;var maximumSampledHeap=0L
        fun save() {
            journalWriter.flush()
            val runtime=Runtime.getRuntime()
            maximumSampledHeap=maxOf(maximumSampledHeap,runtime.totalMemory()-runtime.freeMemory())
            report.put("persisted_cases",completedCases).put("maximum_sampled_java_heap_bytes",maximumSampledHeap)
                .put("java_heap_limit_bytes",runtime.maxMemory())
            val temporary=File(output.parentFile,output.name+".tmp")
            temporary.bufferedWriter().use { writer ->
                writer.write(report.toString().dropLast(1));writer.write(",");writer.write(JSONObject.quote("outcomes"));writer.write(":[")
                var first=true
                journal.useLines { lines -> lines.forEach { line ->
                    if(!first)writer.write(",");writer.write(line);first=false
                }}
                writer.write("]}")
            }
            check(temporary.renameTo(output))
        }
        try {
            args.getString("vipiWitnessSha")?.let { expected ->
                require(expected.matches(Regex("[0-9a-f]{64}")))
                val witnessRevision=args.getString("vipiWitnessRevision") ?: "001"
                require(witnessRevision.matches(Regex("[0-9]{3}")))
                val file=File(context.filesDir,"context-witnesses-$witnessRevision.sqlite")
                check(sha(file)==expected)
                witnessDB=SQLiteDatabase.openDatabase(file.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
                report.put("witness_sha256",expected).put("witness_revision",witnessRevision)
            }
            val shards=manifest.getJSONArray("shards")
            for(i in 0 until shards.length()) {
                val value=shards.getJSONObject(i);val language=value.getString("language")
                require(language.matches(Regex("[a-z]{2}")))
                val file=File(root,"$language.sqlite");assertEquals(value.getLong("bytes"),file.length());assertEquals(value.getString("sha256"),sha(file))
                databases[language]=SQLiteDatabase.openDatabase(file.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
            }
            val input=File(root,"cases.json");assertEquals(manifest.getString("cases_sha256"),sha(input))
            val named="😀 محطة حافلات سوق الذهب إلى المدينة. الفنجان هنا."
            assertEquals(listOf("سوق","الذهب"),LexicalConcordance.namedPlaces(named,"ar").map{named.substring(it)})
            assertTrue(LexicalConcordance.namedPlaces(named,"en").isEmpty())
            witnessDB?.let { witness ->
                val original="I was happy when she arrived."
                fun windows(text:String)=requireNotNull(ReviewedFrameLookup.windows(text,"en")).mapKeys{co.fallsoft.vipi.core.ImmersionEngine.lookupKey(it.key)}
                val release=databases.getValue("en").rawQuery("SELECT value FROM metadata WHERE key='release_id'",null).use { c -> check(c.moveToFirst());org.json.JSONTokener(c.getString(0)).nextValue() as String }
                val evidence=requireNotNull(ContextWitnessLookup.load(witness,original,"en","es",release,setOf("when"),setOf("cuando")))
                assertTrue(evidence.supports("when","cuando",12 until 16,original,windows(original)))
                val separated="I was happy. when she arrived."
                assertFalse(requireNotNull(ContextWitnessLookup.load(witness,separated,"en","es",release,setOf("when"),setOf("cuando"))).supports("when","cuando",13 until 17,separated,windows(separated).filterKeys{it=="was"}))
                val entries=LexicalConcordance.entries(databases.getValue("en"),databases.getValue("es"),original,"Estaba feliz cuando ella llegó.","en","es",witness)
                assertFalse("Context agreement must not bypass grammatical source guards",entries.any{it.source=="when"})
                val common=LexicalConcordance.entries(databases.getValue("en"),databases.getValue("es"),"I am at my house.","Estoy en mi casa.","en","es",witness)
                assertTrue("A differently capitalized surname must not erase a corroborated common word",common.any{it.source=="house" && "casa" in it.targets})
                val name=LexicalConcordance.entries(databases.getValue("en"),databases.getValue("es"),"I spoke to House.","Hablé con Casa.","en","es",witness)
                assertFalse("A proper name must remain protected even when the supplied translation gets it wrong",name.any{it.source=="House"})
                val alias=LexicalConcordance.entries(databases.getValue("zh"),databases.getValue("en"),"今晚放假了，有什么节目啊？","Tonight, have a holiday, what is the show?","zh","en",witness)
                assertFalse("Alternate-script grammatical analyses must remain visible",alias.any{it.source=="什么"})
                report.put("context_guard_checks",true)
            }
            val cases=JSONArray(input.readText());val catalog=BundledImmersionCatalog(context)
            for(i in 0 until cases.length()) {
                val row=cases.getJSONObject(i);val source=row.getString("source");val target=row.getString("target")
                val original=row.getString("original");val translation=row.getString("translation")
                val intact=TranslationIntegrity.preservesIdentifiers(original,translation)
                val diagnostic=mutableMapOf<String,Int>()
                val start=System.nanoTime()
                val entries=if(intact)LexicalConcordance.entries(databases.getValue(source),databases.getValue(target),original,translation,source,target,witnessDB) {key->diagnostic[key]=(diagnostic[key] ?: 0)+1} else emptyList()
                val result=LocalImmersion.align(original,translation,entries,1.0,source,target)
                val elapsed=(System.nanoTime()-start)/1e6
                val previous=if(intact)catalog.result(original,translation,source,target,1.0) else null
                val combinedStart=System.nanoTime()
                val combined=if(intact)catalog.result(original,translation,source,target,1.0,entries) else result
                val combinedElapsed=elapsed+(System.nanoTime()-combinedStart)/1e6
                val baselineRetained=previous?.spans.orEmpty().all { it in combined.spans }
                if(!baselineRetained)failures.put(row.getString("id")+": combined catalog lost an accepted baseline span")
                assertEquals(original,result.original);assertEquals(translation,result.translation)
                assertEquals(original,result.speech(source,target,result.spans.map{it.id}.toSet()).joinToString(""){it.text})
                if(target in setOf("ar","zh","ja","ko"))assertTrue(result.spans.all{!it.romanization.isNullOrBlank()})
                val spans=JSONArray()
                for(span in result.spans)spans.put(JSONObject().put("source",span.original).put("target",span.translated)
                    .put("start",span.start).put("end",span.end).put("target_start",span.targetStart).put("target_end",span.targetEnd)
                    .put("reading",span.romanization ?: JSONObject.NULL))
                val combinedSpans=JSONArray()
                for(span in combined.spans)combinedSpans.put(JSONObject().put("source",span.original).put("target",span.translated)
                    .put("start",span.start).put("end",span.end).put("target_start",span.targetStart).put("target_end",span.targetEnd)
                    .put("reading",span.romanization ?: JSONObject.NULL))
                assertEquals(original,combined.speech(source,target,combined.spans.map{it.id}.toSet()).joinToString(""){it.text})
                val sourceTokens=JSONArray()
                for(range in LocalImmersion.words(original,source))sourceTokens.put(JSONArray().put(range.first).put(range.last+1))
                val outcome=JSONObject().put("source_token_ranges",sourceTokens).put("id",row.getString("id")).put("dataset",row.getString("dataset"))
                    .put("source",source).put("target",target).put("spans",spans)
                    .put("baseline_spans",previous?.spans?.size ?: 0).put("elapsed_ms",elapsed).put("identifier_guard",intact).put("diagnostics",JSONObject(diagnostic as Map<*,*>))
                    .put("combined_spans",combinedSpans).put("combined_elapsed_ms",combinedElapsed).put("baseline_retained",baselineRetained)
                journalWriter.write(outcome.toString());journalWriter.newLine();completedCases++
                if(i%100==0)save()
                fun forbidden(span:co.fallsoft.vipi.core.ImmersionSpan)=row.has("forbidden_source") && span.original==row.getString("forbidden_source") && span.translated==row.getString("forbidden_target") &&
                    (!row.has("forbidden_source_start") || span.start==row.getInt("forbidden_source_start"))
                if(result.spans.any(::forbidden))
                    failures.put(row.getString("id")+": known meaning/scope error")
                if(combined.spans.any(::forbidden))
                    failures.put(row.getString("id")+": combined known meaning/scope error")
                if(row.has("expected_source")) {
                    val expectedPath=row.optString("expected_path","dictionary")
                    require(expectedPath in setOf("dictionary","combined"))
                    val expected=if(expectedPath=="combined")combined else result
                    fun matches(span:co.fallsoft.vipi.core.ImmersionSpan)=span.original==row.getString("expected_source") && span.translated==row.getString("expected_target")
                    if(expected.spans.none{matches(it)})failures.put(row.getString("id")+": missing required lexical behavior")
                    if(combined.spans.none{matches(it)})failures.put(row.getString("id")+": combined missing required lexical behavior")
                    if(row.has("expected_count") && (expected.spans.count(::matches)!=row.getInt("expected_count") || combined.spans.count(::matches)!=row.getInt("expected_count")))
                        failures.put(row.getString("id")+": repeated lexical occurrence count")
                    if(row.optBoolean("expected_dictionary_abstention",false) && result.spans.any{matches(it)})
                        failures.put(row.getString("id")+": dictionary phrase protection was bypassed")
                }
            }
            report.put("complete",true).put("cases",cases.length()).put("failures",failures).put("passed",failures.length()==0);save()
            assertEquals(failures.toString(),0,failures.length())
        } finally {journalWriter.close();witnessDB?.close();databases.values.forEach{it.close()}}
    }
}
