package co.fallsoft.vipi.contextqa

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.contextqa.FrozenContextTokenizer.Range
import org.json.JSONTokener
import org.json.JSONArray

/** Indexed public dictionary evidence. No generated translations or stems. */
internal object PristineLexicalSource {
    private val POLICIES=setOf("native-linked-analysis-concordance-2","native-linked-lexical-units-3","native-linked-lexical-units-4","native-linked-noun-carriers-5","native-linked-modern-lexemes-6","native-linked-chinese-lexical-7","native-linked-noun-gloss-articles-8","native-linked-adjective-agreement-10","native-linked-swahili-reviewed-13","native-linked-swahili-object-carriers-15","native-linked-arabic-plural-readings-16","native-linked-attested-past-verbs-17","native-linked-attested-present-verbs-18")
    private const val SURFACE_READING_RULE="supplied-arabic-plural-reading-1"
    private const val PAST_READING_RULE="supplied-past-verb-reading-1"
    private const val PAST_RULE="attested-positive-past-verb-1"
    private const val PRESENT_RULE="attested-positive-present-verb-1"
    private val SURFACE_READING_RULES=setOf(SURFACE_READING_RULE,PAST_READING_RULE)
    private val finitePastSubject=Regex("(?i)(?<![\\p{L}\\p{M}\\p{N}_])(?:i|you|he|she|it|we|they)[ \\t]+$")
    internal fun hasFinitePastSubject(text:String,start:Int):Boolean =
        start in 0..text.length && finitePastSubject.containsMatchIn(text.substring(0,start))
    private data class Form(val key:String,val lexeme:Long,val written:String,val start:Int,val end:Int,
        val number:Int,val mode:Int,val sourceSafe:Boolean,val targetSafe:Boolean,val features:Set<String>,val pos:String,val proper:Boolean,val grammar:Boolean,val head:String)
    private data class Term(val sense:String,val reading:String,val eligible:Boolean,val explicit:Boolean,val family:String)
    private data class Side(val windows:Map<String,List<IntRange>>,val forms:Map<String,List<Form>>,
        val terms:Map<Long,List<Term>>,val surfaceReadings:Map<Pair<Long,String>,Map<String,Set<String>>>,val blocked:Set<String>,val targetBlocked:Set<String>,val names:Set<String>,val guards:Set<String>,val inventory:String,val release:String,val namedPlaces:List<IntRange>,val phrases:List<IntRange>)
    private class Overflow:Exception()
    private fun key(value:String)=NativeGeometry.lookupKey(value)
    private fun marks(count:Int)=List(count){"?"}.joinToString(",")
    private val sentenceText=Regex("[^.!?。！？؛;؟\\r\\n]+")
    private class SentenceAlignment(original:String,translation:String) {
        private fun scopes(text:String)=sentenceText.findAll(text).filter{it.value.any(Char::isLetterOrDigit)}.map{it.range}.toList()
        private val sources=scopes(original);private val targets=scopes(translation)
        fun uniqueSource(source:IntRange,occurrences:List<IntRange>):Boolean {
            val sentence=sources.firstOrNull{it.first<=source.first && it.last>=source.last} ?: return false
            return occurrences.distinct().count{it.first>=sentence.first && it.last<=sentence.last}==1
        }
        fun permits(source:IntRange,target:IntRange):Boolean {
            // Matching sentence counts provide a conservative positional veto.
            // Different punctuation structures are not asserted to be aligned.
            if(sources.size<=1 || sources.size!=targets.size)return true
            val a=sources.indexOfFirst{it.first<=source.first && it.last>=source.last}
            val b=targets.indexOfFirst{it.first<=target.first && it.last>=target.last}
            return a>=0 && a==b
        }
    }
    // Keep following place names original in a script without capitals.
    private val arabicPlace=Regex("(?:^|[\\s،؛:,.!?])[وفبلك]?(?:محطة(?:\\s+(?:حافلات|قطارات|قطار|مترو))*|فندق|مطار|شارع|جامعة|مطعم)\\s+")
    private val arabicNameWord=Regex("[\\p{L}\\p{M}]+")
    private val nameStops=setOf("من","إلى","الى","في","على","عند","عن","و","أو","هل","هو","هي","هذا","هذه")
    // Preserve the complete idiom, including common SMS article spellings.
    // "Free all e way until two" does not refer to a road. Whole-phrase
    // mappings remain possible; only a contained literal fragment is blocked.
    private val englishAllTheWay=Regex("(?<![\\p{L}\\p{M}\\p{N}_])all\\s+(?:the|e|d)\\s+way(?![\\p{L}\\p{M}\\p{N}_])",RegexOption.IGNORE_CASE)
    private val englishLectureShorthand=Regex("(?<![\\p{L}\\p{M}\\p{N}_])(?:finish\\s+lect|lect\\s+finishes)(?![\\p{L}\\p{M}\\p{N}_])",RegexOption.IGNORE_CASE)
    // Spaced homework is one lexical unit; a generic "works" fragment
    // would teach the wrong sense. Whole-unit mappings remain eligible.
    private val englishSpacedHomework=Regex("(?<![\\p{L}\\p{M}\\p{N}_])home\\s+works?(?![\\p{L}\\p{M}\\p{N}_])",RegexOption.IGNORE_CASE)
    private fun phrases(text:String,language:String):List<IntRange> =
        if(language=="en")(englishAllTheWay.findAll(text)+englishLectureShorthand.findAll(text)+englishSpacedHomework.findAll(text)).map{it.range}.toList() else emptyList()
    internal fun namedPlaces(text:String,language:String):List<IntRange> {
        if(language!="ar")return emptyList()
        val output=mutableListOf<IntRange>()
        for(prefix in arabicPlace.findAll(text)) {
            var position=prefix.range.last+1
            for(i in 0 until 4) {
                val token=arabicNameWord.find(text,position) ?: break
                if(token.range.first!=position || key(token.value) in nameStops)break
                output+=token.range;position=token.range.last+1
                while(position<text.length && text[position].isWhitespace())position++
            }
        }
        return output
    }
    private fun load(db:SQLiteDatabase,text:String,language:String):Side? {
        val metadata=mutableMapOf<String,String>()
        db.rawQuery("SELECT key,value FROM metadata WHERE key IN ('schema','policy','language','source_inventory_sha256','release_id','surface_reading_schema','surface_reading_rule','whole_verb_schema','whole_verb_rule','present_verb_schema','present_verb_rule')",null).use { c ->
            while(c.moveToNext())metadata[c.getString(0)]=JSONTokener(c.getString(1)).nextValue() as String
        }
        val inventory=requireNotNull(metadata.remove("source_inventory_sha256"));require(inventory.matches(Regex("[0-9a-f]{64}")))
        val release=requireNotNull(metadata.remove("release_id"));require(release.matches(Regex("[0-9a-f]{64}")))
        val policy=metadata.remove("policy");require(policy in POLICIES)
        val hasPresent=policy=="native-linked-attested-present-verbs-18"
        if(hasPresent) {
            require(language in setOf("en","es","fr","de","pt") && metadata.remove("present_verb_schema")=="vipi-whole-present-verb-1")
            require(metadata.remove("present_verb_rule")==PRESENT_RULE)
        }
        val hasPast=policy=="native-linked-attested-past-verbs-17" || (hasPresent && language=="en")
        if(hasPast) {
            require(language in setOf("en","ja","ko") && metadata.remove("whole_verb_schema")=="vipi-whole-past-verb-1")
            require(metadata.remove("whole_verb_rule")==PAST_RULE)
        }
        val hasSurfaceReadings=policy=="native-linked-arabic-plural-readings-16" || (hasPast && language!="en")
        if(hasSurfaceReadings) {
            require((hasPast || language=="ar") && metadata.remove("surface_reading_schema")=="vipi-surface-reading-2")
            require(metadata.remove("surface_reading_rule")==if(hasPast) PAST_READING_RULE else SURFACE_READING_RULE)
        }
        require(metadata==mapOf("schema" to "vipi-lexical-shard-2","language" to language))
        val raw=ReviewedFrameLookup.windows(text,language) ?: return null
        val windows=linkedMapOf<String,MutableList<IntRange>>()
        for((written,ranges) in raw)windows.getOrPut(key(written)){mutableListOf()}.addAll(ranges)
        val forms=linkedMapOf<String,MutableList<Form>>();val blocked=mutableSetOf<String>();val guards=mutableSetOf<String>();val targetBlocked=mutableSetOf<String>();val names=mutableSetOf<String>()
        var count=0
        for(batch in windows.keys.sorted().chunked(200)) {
            db.rawQuery("SELECT s.normalized,s.lexeme,s.surface,s.start,s.end,s.number,s.mode,l.source_safe,l.target_safe,s.features,l.pos,g.reason,COALESCE(g.target_blocked,0),l.normalized FROM surfaces s JOIN lexemes l ON l.id=s.lexeme LEFT JOIN guards g ON g.normalized=l.normalized WHERE s.normalized IN (${marks(batch.size)}) ORDER BY s.normalized,s.lexeme",batch.toTypedArray()).use { c ->
                while(c.moveToNext()) {
                    count++;if(count>16384)throw Overflow()
                    val form=Form(c.getString(0),c.getLong(1),c.getString(2),c.getInt(3),c.getInt(4),c.getInt(5),c.getInt(6),c.getInt(7)==1,c.getInt(8)==1,JSONArray(c.getString(9)).let{a->(0 until a.length()).map{a.getString(it)}.toSet()},c.getString(10),c.getString(10) in setOf("name","proper-noun","proper_noun"),c.getString(10) in setOf("pron","det","prep","postp","conj","particle","article","aux") || c.getString(11)=="grammar" || c.getInt(12)==1,c.getString(13))
                    val values=forms.getOrPut(form.key){mutableListOf()}
                    if(values.size<256)values+=form else {blocked+=form.key;targetBlocked+=form.key}
                }
            }
            db.rawQuery("SELECT normalized,blocked,target_blocked,protect_inner,reason FROM guards WHERE normalized IN (${marks(batch.size)})",batch.toTypedArray()).use { c ->
                while(c.moveToNext()) {if(c.getInt(1)==1)blocked+=c.getString(0);if(c.getInt(2)==1)targetBlocked+=c.getString(0);if(c.getInt(3)==1)guards+=c.getString(0);if(c.getString(4)=="name")names+=c.getString(0)}
            }
        }
        val terms=linkedMapOf<Long,MutableList<Term>>()
        count=0
        for(batch in forms.values.flatten().map{it.lexeme}.distinct().sorted().chunked(200)) {
            db.rawQuery("SELECT t.lexeme,t.sense,t.reading,t.eligible,s.explicit,s.source_url FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme IN (${marks(batch.size)}) ORDER BY t.lexeme,t.sense,t.reading",batch.map{it.toString()}.toTypedArray()).use { c ->
                while(c.moveToNext()) {
                    count++;if(count>32768)throw Overflow()
                    terms.getOrPut(c.getLong(0)){mutableListOf()}.add(Term(c.getString(1),c.getString(2),c.getInt(3)==1,c.getInt(4)==1,c.getString(5)))
                }
            }
        }
        val surfaceReadings=linkedMapOf<Pair<Long,String>,MutableMap<String,MutableSet<String>>>()
        if(hasSurfaceReadings) {
            count=0
            for(batch in windows.keys.sorted().chunked(200)) {
                db.rawQuery("SELECT lexeme,normalized,reading,sense FROM surface_readings WHERE normalized IN (${marks(batch.size)}) ORDER BY normalized,lexeme,reading",batch.toTypedArray()).use { c ->
                    while(c.moveToNext()) {
                        count++;if(count>16384)throw Overflow()
                        val reading=c.getString(2);require(reading.isNotEmpty() && reading.length<=96)
                        surfaceReadings.getOrPut(c.getLong(0) to c.getString(1)){linkedMapOf()}
                            .getOrPut(c.getString(3)){mutableSetOf()}.add(reading)
                    }
                }
            }
        }
        return Side(windows,forms,terms,surfaceReadings,blocked,targetBlocked,names,guards,inventory,release,namedPlaces(text,language),phrases(text,language))
    }
    /** Additive English-only observations. No target or display approval. */
    fun inspect(db:SQLiteDatabase, original:String, language:String, protection:List<Range>):LexicalSourceRecognition.Snapshot? {
        if(language!="en" || original.length>16384 || original.codePoints().toArray().any{it in 0xd800..0xdfff} || protection.size>4096 || protection.any{!LexicalSourceRecognition.valid(it,original)})return null
        val side=load(db,original,language) ?: return null
        val units=mutableListOf<LexicalSourceRecognition.Unit>();var occurrences=0
        for(word in side.windows.keys.sorted()) {
            val raw=side.forms[word].orEmpty()
            if(raw.isEmpty() && word !in side.blocked && word !in side.targetBlocked && word !in side.names && word !in side.guards)continue
            val forms=raw.map { f ->
                val focus=LexicalSourceRecognition.intrinsic(f.mode,f.start,f.end,f.written)
                LexicalSourceRecognition.Form(f.lexeme.toString(),f.written,focus,f.number,f.mode,f.sourceSafe,f.targetSafe,f.features.toSet(),f.pos,f.proper,f.grammar,f.head)
            }
            for(r in side.windows[word].orEmpty().sortedWith(compareBy<IntRange>{it.first}.thenBy{it.last})) {
                val range=Range(r.first,r.last+1)
                if(!LexicalSourceRecognition.valid(range,original) || units.size>=4096 || occurrences>16384-forms.size)return null
                occurrences+=forms.size
                units+=LexicalSourceRecognition.Unit(word,range,original.substring(r),word in side.blocked,word in side.targetBlocked,word in side.names,word in side.guards,forms)
            }
        }
        val names=side.namedPlaces.map{Range(it.first,it.last+1)};val phrases=side.phrases.map{Range(it.first,it.last+1)}
        if((names+phrases).any{!LexicalSourceRecognition.valid(it,original)})return null
        return LexicalSourceRecognition.Snapshot(original,language,side.release,side.inventory,protection.toList(),names,phrases,units.toList())
    }
}
