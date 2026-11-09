package co.fallsoft.vipi.contextqa
import android.app.Instrumentation
import android.os.Bundle
import android.os.Debug
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import co.fallsoft.vipi.contextqa.FrozenContextTokenizer.Range

class ContextProbeInstrumentation:Instrumentation() {
    private lateinit var args:Bundle
    private var outputBytes=0L
    private val started=System.nanoTime()
    override fun onCreate(arguments:Bundle?) { super.onCreate(arguments);args=arguments?:Bundle();start() }
    private fun json(name:String)=JSONObject(targetContext.assets.open(name).bufferedReader().use{it.readText()})
    private fun arr(values:Iterable<Any?>)=JSONArray().also{a->values.forEach{a.put(it?:JSONObject.NULL)}}
    private fun range(r:Range)=arr(listOf(r.start,r.end-r.start))
    private fun ranges(a:JSONArray,length:Boolean)= (0 until a.length()).map { val r=a.getJSONArray(it);Range(r.getInt(0),if(length)r.getInt(0)+r.getInt(1) else r.getInt(1)) }
    private fun strings(a:JSONArray)=(0 until a.length()).map{a.getString(it)}
    private fun words(s:String)=NativeGeometry.words(s,"en").map{Range(it.first,it.last+1)}
    private fun emit(kind:String,value:JSONObject) {
        val text=JSONObject().put("kind",kind).put("value",value).toString()
        outputBytes+=text.toByteArray().size;require(outputBytes<=16L*1024*1024)
        sendStatus(1,Bundle().apply{putString("stream","CONTEXT_ROW:$text\n")})
    }
    private fun failExpected(name:String,action:()->Unit) {
        var rejected=false
        try { action() } catch(_:IllegalArgumentException){rejected=true}
        require(rejected){"Expected rejection: $name"};emit("negative",JSONObject().put("name",name).put("rejected",true))
    }
    private fun memory():JSONObject {
        val m=Debug.MemoryInfo();Debug.getMemoryInfo(m);val r=Runtime.getRuntime()
        return JSONObject().put("pss_kib",m.totalPss).put("java_used",r.totalMemory()-r.freeMemory())
            .put("java_max",r.maxMemory()).put("native_allocated",Debug.getNativeHeapAllocatedSize())
            .put("process_status",File("/proc/self/status").readLines().filter{it.startsWith("VmHWM:")||it.startsWith("VmRSS:")}.joinToString("\n"))
    }
    private fun snapshot(s:LexicalSourceRecognition.Snapshot):JSONObject = JSONObject()
        .put("original",s.original).put("language",s.language).put("release",s.dictionaryRelease).put("inventory",s.dictionaryInventory)
        .put("supplied",arr(s.suppliedProtection.map(::range))).put("named_places",arr(s.namedPlaces.map(::range))).put("phrases",arr(s.phraseRanges.map(::range)))
        .put("units",arr(s.units.map { u -> JSONObject().put("key",u.key).put("range",range(u.range)).put("original",u.original)
            .put("source_blocked",u.sourceBlocked).put("target_blocked",u.targetBlocked).put("name_guard",u.hasNameGuard).put("protects_inner",u.protectsInner)
            .put("forms",arr(u.forms.map { f -> JSONObject().put("lexeme",f.lexemeID).put("written",f.written)
                .put("intrinsic",f.intrinsicRange?.let(::range)?:JSONObject.NULL).put("mode",f.mode).put("number",f.number)
                .put("source_safe",f.sourceSafe).put("target_safe",f.targetSafe).put("features",arr(f.features.sorted()))
                .put("pos",f.partOfSpeech).put("proper",f.isProperName).put("grammar",f.isGrammar).put("head",f.headword) })) }))
    override fun onStart() {
        val receipt=JSONObject().put("scope","Isolated evidence only; no admission or app activation")
        try {
            val inputs=File(requireNotNull(targetContext.getExternalFilesDir(null)),"context-inputs")
            if(args.getString("mode")=="prepare") {
                require(inputs.mkdirs() || inputs.isDirectory)
                finish(-1,Bundle().apply{putString("stream","CONTEXT_PREPARED:${inputs.absolutePath}\n")});return
            }
            require(args.getString("mode")=="probe")
            receipt.put("memory_before",memory())
            val table=targetContext.assets.open("unicode15.json").use{it.readBytes()};val tokenizer=FrozenContextTokenizer(table)
            val tokenCases=json("tokenizer-fixtures.json").getJSONArray("cases");require(tokenCases.length()==22)
            for(i in 0 until tokenCases.length()) {
                val c=tokenCases.getJSONObject(i);val text=c.getString("source")
                if(!c.getBoolean("supported")){failExpected("unsupported_unicode_$i"){tokenizer.tokenize(text)};continue}
                val got=tokenizer.tokenize(text);val expected=c.getJSONArray("tokens");require(got.size==expected.length())
                got.forEachIndexed { j,t -> val e=expected.getJSONObject(j)
                    require(t.original==e.getString("text") && t.normalized==e.getString("normalized") && t.hasAlphabeticScalar==e.getBoolean("has_alpha"))
                    require(t.range==ranges(JSONArray().put(e.getJSONArray("range")),true).single())
                }
                require(tokenizer.normalize(text)==c.getString("normalized"))
                emit("unicode",JSONObject().put("index",i).put("source",text).put("normalized",tokenizer.normalize(text)).put("tokens",arr(got.map{JSONObject().put("text",it.original).put("normalized",it.normalized).put("range",range(it.range)).put("has_alpha",it.hasAlphabeticScalar)})))
            }
            failExpected("unpaired_surrogate"){tokenizer.tokenize("\uD800")}
            failExpected("source_bound"){tokenizer.normalize("a".repeat(16385))}
            // U+0344 canonically decomposes to two marks. The bound applies to
            // the original 16384 UTF16 units, not to the expanded NFC output.
            val expanded=tokenizer.normalize("\u0344".repeat(16384));require(expanded=="\u0308\u0301".repeat(16384))
            emit("negative",JSONObject().put("name","NFC_expansion_source_only_bound").put("passed",true))
            val binding=json("native-bindings.json");val metadata=binding.getJSONObject("expected_metadata")
            val expected=metadata.keys().asSequence().associateWith{metadata.getString(it)}
            val packFile=File(inputs,"context.sqlite");val dictionaries=mapOf("en" to File(inputs,"d-en.sqlite"),"es" to File(inputs,"d-es.sqlite"))
            fun load(file:File=packFile,sha:String=binding.getString("pack_sha256"))=FrozenContextPackReader(file,sha,expected,dictionaries,tokenizer)
            val begin=System.nanoTime();val pack=load();receipt.put("reader_load_and_hash_ns",System.nanoTime()-begin)
            failExpected("wrong_pack_identity"){load(sha="0".repeat(64))}
            val dummy=File(targetContext.cacheDir,"sidecar-probe.sqlite");require(!dummy.exists());packFile.copyTo(dummy)
            require(dummy.length()==packFile.length()) // Same valid pack: sidecar is the only changed input.
            for(suffix in listOf("-wal","-shm","-journal")) {
                val sidecar=File(dummy.path+suffix);sidecar.writeBytes(byteArrayOf())
                try{failExpected("sidecar_$suffix"){load(dummy)}}finally{require(sidecar.delete())}
            };require(dummy.delete())
            failExpected("offset_split_surrogate"){pack.assess("😀 dog",listOf(Range(1,2)),Range(1,2),emptyList())}
            failExpected("negative_offset"){pack.assess("dog",listOf(Range(-1,3)),Range(-1,3),emptyList())}
            failExpected("malformed_source_key"){pack.assess("dog",listOf(Range(0,3)),Range(0,3),listOf("[1]"))}
            val rows=json("rule-fixtures.json").getJSONArray("rows");require(rows.length()==1157)
            var noHead=0
            for(i in 0 until rows.length()) {
                val row=rows.getJSONObject(i);require(row.getBoolean("roundtrip"));val text=row.getString("source")
                val focus=ranges(JSONArray().put(row.getJSONArray("focus")),true).single();val native=words(text)
                val out=JSONObject().put("index",i).put("rule_id",row.getString("rule_id")).put("native",arr(native.map(::range)))
                if(focus !in native)out.put("status","native_geometry_difference")
                else {
                    val result=pack.assess(text,native,focus,strings(row.getJSONArray("source_keys")));val winner=result.winner
                    val expect=row.optJSONObject("winner")
                    val equal=winner?.rule?.id==expect?.getString("id") && winner?.rule?.headIDs==expect?.getJSONArray("head_ids")?.let(::strings)
                    out.put("winner",winner?.rule?.id?:JSONObject.NULL).put("heads",arr(winner?.rule?.headIDs.orEmpty())).put("expected_equal",equal)
                    out.put("context",winner?.contextRange?.let(::range)?:JSONObject.NULL)
                    out.put("whole_native_geometry_equal",native==ranges(row.getJSONArray("ranges"),true))
                    if(native==ranges(row.getJSONArray("ranges"),true))require(equal){"Fixture mismatch $i"}
                    if(winner!=null && winner.rule.headIDs.isEmpty())noHead++
                };emit("rule",out)
            }
            receipt.put("no_head_winners",noHead)
            val keys=pack.rules.map{it.sourceKey}.distinct().groupBy{JSONArray(it).getString(0)}
            val full=json("full-sources.json").getJSONArray("cases");require(full.length()==52)
            SQLiteDatabase.openDatabase(dictionaries.getValue("en").path,null,SQLiteDatabase.OPEN_READONLY).use { db ->
                var nilFocus=0
                for(i in 0 until full.length()) {
                    val row=full.getJSONObject(i);val source=row.getString("source");val native=words(source)
                    val protection=ranges(row.getJSONArray("protected_ranges_utf16"),false)
                    val snap=requireNotNull(PristineLexicalSource.inspect(db,source,"en",protection))
                    require(snap.matches(source,"en",snap.dictionaryRelease,snap.dictionaryInventory,protection))
                    require(!snap.matches(source+" ","en",snap.dictionaryRelease,snap.dictionaryInventory,protection))
                    nilFocus+=snap.units.sumOf{u->u.forms.count{it.intrinsicRange==null}}
                    val focuses=native.mapNotNull { focus -> val spelling=tokenizer.normalize(source.substring(focus.start,focus.end));val sourceKeys=keys[spelling]?:return@mapNotNull null
                        val a=pack.assess(source,native,focus,sourceKeys)
                        JSONObject().put("focus",range(focus)).put("source",source.substring(focus.start,focus.end)).put("winner",a.winner?.rule?.id?:JSONObject.NULL)
                            .put("geometry_rejections",arr(a.rawMatches.filter{!it.contextGeometryCompatible}.map{it.rule.id})) }
                    emit("full_source",JSONObject().put("index",i).put("case_id",row.getString("case_id")).put("source_id",row.getString("source_id"))
                        .put("native",arr(native.map(::range))).put("focuses",arr(focuses)).put("snapshot",snapshot(snap)))
                }
                receipt.put("nil_intrinsic_focus_occurrences",nilFocus)
                for(source in listOf("is","are","has")) {
                    val s=requireNotNull(PristineLexicalSource.inspect(db,source,"en",emptyList()))
                    require(s.units.any{u->u.forms.any{it.mode==0 && it.intrinsicRange==null}})
                    emit("sentinel",snapshot(s))
                }
                val supplied=listOf(Range(0,3));val s=requireNotNull(PristineLexicalSource.inspect(db,"dog","en",supplied))
                require(s.suppliedProtection==supplied && s.hasStructuralProtection(Range(0,3)))
                require(PristineLexicalSource.inspect(db,"dog","en",listOf(Range(0,4)))==null)
            }
            failExpected("positive_mode_zero_focus"){LexicalSourceRecognition.intrinsic(1,0,0,"is")}
            failExpected("invalid_intrinsic_end"){LexicalSourceRecognition.intrinsic(1,0,8,"is")}
            // One run of the retained 148 sources for new source-bound adapter
            // parity only. This does not repeat historical 3-pass engine QA.
            val modelDir=File(targetContext.filesDir,"models");modelDir.mkdirs()
            val pins=json("model-pins.json");val modelPins=pins.keys().asSequence().associateWith{pins.getString(it)}
            for(name in modelPins.keys)targetContext.assets.open(name).use{input->File(modelDir,name).outputStream().use{input.copyTo(it)}}
            val modelStart=System.nanoTime();val provider=EnglishSourceRoleProvider(modelDir,modelPins)
            receipt.put("model_load_ns",System.nanoTime()-modelStart)
            val roleCases=json("role-inputs.json").getJSONArray("cases");require(roleCases.length()==148)
            for(i in 0 until roleCases.length()) {
                val c=roleCases.getJSONObject(i);val text=c.getString("text");val native=words(text)
                val r=provider.inspect(text,"en",native,emptyList());require(r.snapshot.status==EnglishRoleEvidence.Status.READY)
                require(r.snapshot.namedProtection==EnglishRoleEvidence.NamedProtection.UNAVAILABLE)
                emit("role",JSONObject().put("index",i).put("id",c.getString("id")).put("source_sha256",FrozenContextTokenizer.sha256(text.toByteArray()))
                    .put("tokens",arr(r.tokens.map{JSONObject().put("range",range(it.range)).put("text",it.original).put("tag",it.rawTag).put("score",it.score)}))
                    .put("observations",arr(r.snapshot.observations.map{JSONObject().put("range",range(it.range)).put("role",it.role.name).put("unknown",it.unknownReason?:JSONObject.NULL)})))
            }
            val exact=words("dog");val mask=listOf(Range(0,3));val protected=provider.inspect("dog","en",exact,mask).snapshot
            require(protected.suppliedProtection==mask && protected.observations.single().overlapsSuppliedProtection)
            require(protected.matches("dog","en",exact,mask,modelPins))
            require(!protected.matches("Dog","en",exact,mask,modelPins))
            require(!protected.matches("dog","en",exact,emptyList(),modelPins))
            require(provider.inspect("dog","en",listOf(Range(0,2)),mask).snapshot.status==EnglishRoleEvidence.Status.GEOMETRY_MISMATCH)
            require(provider.inspect("dog","es",exact,mask).snapshot.suppliedProtection==mask)
            require(provider.inspect("\uD800","en",emptyList(),emptyList()).snapshot.status==EnglishRoleEvidence.Status.INVALID_INPUT)
            receipt.put("success",true).put("memory_after",memory()).put("end_to_end_probe_ns",System.nanoTime()-started)
            finish(-1,Bundle().apply{putString("stream","CONTEXT_RECEIPT:$receipt\n")})
        } catch(e:Throwable) {
            receipt.put("success",false).put("error",e.stackTraceToString()).put("memory_final",memory())
            finish(0,Bundle().apply{putString("stream","CONTEXT_RECEIPT:$receipt\n")})
        }
    }
}
