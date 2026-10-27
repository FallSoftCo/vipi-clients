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
        val output=File(context.filesDir,"lexical-coverage-$revision.json");check(!output.exists())
        val failures=JSONArray();val outcomes=JSONArray();val report=JSONObject().put("schema","vipi-lexical-coverage-1")
            .put("run",revision).put("fixture",fixture).put("manifest_sha256",sha(File(root,"manifest.json"))).put("platform","android")
            .put("translation_reused",true).put("classification_exercised",false)
            .put("independent_semantic_acceptance",false).put("outcomes",outcomes)
        try {
            val shards=manifest.getJSONArray("shards")
            for(i in 0 until shards.length()) {
                val value=shards.getJSONObject(i);val language=value.getString("language")
                require(language.matches(Regex("[a-z]{2}")))
                val file=File(root,"$language.sqlite");assertEquals(value.getLong("bytes"),file.length());assertEquals(value.getString("sha256"),sha(file))
                databases[language]=SQLiteDatabase.openDatabase(file.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
            }
            val input=File(root,"cases.json");assertEquals(manifest.getString("cases_sha256"),sha(input))
            val cases=JSONArray(input.readText());val catalog=BundledImmersionCatalog(context)
            for(i in 0 until cases.length()) {
                val row=cases.getJSONObject(i);val source=row.getString("source");val target=row.getString("target")
                val original=row.getString("original");val translation=row.getString("translation")
                val intact=TranslationIntegrity.preservesIdentifiers(original,translation)
                val diagnostic=mutableMapOf<String,Int>()
                val start=System.nanoTime()
                val entries=if(intact)LexicalConcordance.entries(databases.getValue(source),databases.getValue(target),original,translation,source,target) {key->diagnostic[key]=(diagnostic[key] ?: 0)+1} else emptyList()
                val result=LocalImmersion.align(original,translation,entries,1.0,source,target)
                val elapsed=(System.nanoTime()-start)/1e6
                val previous=if(intact)catalog.result(original,translation,source,target,1.0) else null
                assertEquals(original,result.original);assertEquals(translation,result.translation)
                assertEquals(original,result.speech(source,target,result.spans.map{it.id}.toSet()).joinToString(""){it.text})
                if(target in setOf("ar","zh","ja","ko"))assertTrue(result.spans.all{!it.romanization.isNullOrBlank()})
                val spans=JSONArray()
                for(span in result.spans)spans.put(JSONObject().put("source",span.original).put("target",span.translated)
                    .put("start",span.start).put("end",span.end).put("target_start",span.targetStart).put("target_end",span.targetEnd)
                    .put("reading",span.romanization ?: JSONObject.NULL))
                val outcome=JSONObject().put("id",row.getString("id")).put("dataset",row.getString("dataset"))
                    .put("source",source).put("target",target).put("spans",spans)
                    .put("baseline_spans",previous?.spans?.size ?: 0).put("elapsed_ms",elapsed).put("identifier_guard",intact).put("diagnostics",JSONObject(diagnostic as Map<*,*>))
                outcomes.put(outcome)
                if(i%100==0)output.writeText(report.toString())
                if(row.has("forbidden_source") && result.spans.any{it.original==row.getString("forbidden_source") && it.translated==row.getString("forbidden_target")})
                    failures.put(row.getString("id")+": known meaning/scope error")
                if(row.has("expected_source") && result.spans.none{it.original==row.getString("expected_source") && it.translated==row.getString("expected_target")})
                    failures.put(row.getString("id")+": missing required lexical behavior")
            }
            report.put("complete",true).put("cases",cases.length()).put("failures",failures).put("passed",failures.length()==0);output.writeText(report.toString())
            assertEquals(failures.toString(),0,failures.length())
        } finally {databases.values.forEach{it.close()}}
    }
}
