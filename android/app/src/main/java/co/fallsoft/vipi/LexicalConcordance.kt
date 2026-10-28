package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.*
import org.json.JSONTokener
import org.json.JSONArray

/** Indexed public dictionary evidence. No generated translations or stems. */
internal object LexicalConcordance {
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
    private fun key(value:String)=ImmersionEngine.lookupKey(value)
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
    // Number 0 means unmarked, not universally singular. Ordinary nouns in
    // these languages may remain unmarked with plural reference. This never
    // relaxes an explicitly singular form or a verb/grammatical analysis.
    private fun numberCompatible(a:Form,b:Form,source:String,target:String):Boolean {
        if(a.number==b.number)return true
        if(a.pos!="noun" || b.pos!="noun" || a.grammar || b.grammar)return false
        fun unmarked(f:Form,language:String)=language in setOf("zh","ja","ko") &&
            f.number==0 && f.mode in 1..2 &&
            f.features.intersect(setOf("singular","plural","dual")).isEmpty()
        return (a.number==2 && unmarked(b,target)) || (b.number==2 && unmarked(a,source))
    }
    // A homograph's unrelated meaning must not veto a reading after a shared
    // eligible sense has been established. Ambiguity within that sense remains.
    private fun linkedTerms(side:Side,form:Form):List<Term> {
        val terms=side.terms[form.lexeme].orEmpty()
        if(form.features.intersect(SURFACE_READING_RULES).isEmpty())return terms
        if(form.mode !in 3..4)return emptyList()
        val senses=side.surfaceReadings[form.lexeme to form.key].orEmpty().keys
        return terms.filter{it.sense in senses}
    }
    private fun readings(side:Side,form:Form,meanings:Set<String>):List<String> {
        val linked=linkedTerms(side,form).filter{it.eligible && it.sense in meanings}
        if(linked.isEmpty())return emptyList()
        // An inflected carrier needs its own attested reading. Missing or
        // ambiguous form evidence must never borrow the singular headword.
        if(form.features.intersect(SURFACE_READING_RULES).isNotEmpty())
            return if(form.mode in 3..4)side.surfaceReadings[form.lexeme to form.key].orEmpty().filterKeys{it in meanings}.values.flatten().distinct() else emptyList()
        return linked.map{it.reading}.filter{it.isNotEmpty()}.distinct()
    }
    private fun shape(form:Form)=listOf(
        if(form.mode==3)form.start else 0,if(form.mode==3)form.end else 0,
        form.number,if(form.mode==3)3 else 1)
    private fun focus(form:Form,range:IntRange,text:String):IntRange? {
        if(form.mode !in 1..5)return null
        if(form.mode in 1..2)return range
        val actual=text.substring(range)
        if(form.mode in 4..5 && (form.start!=0 || form.end!=actual.length))return null
        // Exact UTF-16 geometry is required for a focus inside an attested
        // carrier. Accent/mark normalization must never shift an offset.
        if(actual.length!=form.written.length || !actual.equals(form.written,ignoreCase=true) ||
            form.start<0 || form.end<=form.start || form.end>actual.length)return null
        val start=range.first+form.start;val end=range.first+form.end
        if((start>0 && Character.isLowSurrogate(text[start])) || (end<text.length && Character.isLowSurrogate(text[end])))return null
        return start until end
    }
    private fun targetCaseMatches(form:Form,range:IntRange,text:String):Boolean {
        val actual=text.substring(range)
        if(actual==form.written)return true
        if(key(actual)!=key(form.written))return false
        // Sentence capitalization changes only the initial letter. An acronym
        // or internal capital cannot borrow a lowercase dictionary analysis.
        if(actual.drop(1)!=form.written.drop(1))return false
        // A lexical word may be sentence-capitalized; mid-sentence capitals
        // cannot silently be reinterpreted from a lowercase dictionary entry.
        if(actual.firstOrNull()?.isUpperCase()==true && form.written.firstOrNull()?.isLowerCase()==true) {
            return WrittenCase.sentenceInitial(text,range.first)
        }
        return actual.firstOrNull()?.isUpperCase()==form.written.firstOrNull()?.isUpperCase()
    }
    private fun containedInPhrase(side:Side,range:IntRange):Boolean = side.phrases.any{it.first<=range.first && it.last>=range.last && it!=range}
    private fun containedInKnownWord(side:Side,range:IntRange):Boolean = side.namedPlaces.any{it.first<=range.last && range.first<=it.last} || containedInPhrase(side,range) || side.guards.any { word ->
        side.windows[word].orEmpty().any { whole -> whole.first<=range.first && whole.last>=range.last && whole!=range }
    }
    private val presentComplements=mapOf("live" to setOf("with"),"work" to setOf("at","from","in","on"),"wait" to setOf("for"),"listen" to setOf("to"),"talk" to setOf("to","with","about"),"speak" to setOf("to","with","about"),"write" to setOf("to","about"),"think" to setOf("about"),"learn" to setOf("about","from"),"help" to setOf("with"),"travel" to setOf("to","from"),"walk" to setOf("to","from"))
    private fun protectedPresent(side:Side,range:IntRange,text:String,language:String):Boolean {
        val pronounUnits=when(language) {
            "en"->mapOf("i miss you" to "miss","i love you" to "love","love you" to "love")
            "es"->mapOf("te amo" to "amar")
            else->emptyMap()
        }
        val pronominal=PresentVerbGrammar.pronominalClause(text,range,language)
        if(language!="en" && !pronominal)return containedInKnownWord(side,range)
        if(side.namedPlaces.any{it.first<=range.last && range.first<=it.last} || containedInPhrase(side,range))return true
        val forms=side.forms[key(text.substring(range))].orEmpty().filter(::completePresent)
        return side.guards.any { word -> side.windows[word].orEmpty().any { whole ->
            if(whole.first>range.first || whole.last<range.last || whole==range)false else {
                val parts=word.split(" ")
                val assessedPronounUnit=pronominal && forms.isNotEmpty() && forms.all{pronounUnits[word]==it.head}
                !assessedPronounUnit && !(language=="en" && whole.first==range.first && parts.size==2 && forms.isNotEmpty() &&
                    forms.all{parts[0]==it.key && parts[1] in presentComplements[it.head].orEmpty()})
            }
        }}
    }
    private fun protectedTarget(side:Side,range:IntRange,text:String,language:String,features:Set<String>):Boolean {
        if(side.namedPlaces.any{it.first<=range.last && range.first<=it.last} || containedInPhrase(side,range))return true
        val people=features.intersect(setOf("first-person","second-person","third-person"))
        val numbers=features.intersect(setOf("singular","plural"))
        val subjects=if(language=="en" && "present" in features && people.size==1 && numbers.size==1) {
            when(people.single()+":"+numbers.single()) {
                "first-person:singular"->setOf("i");"first-person:plural"->setOf("we")
                "second-person:singular","second-person:plural"->setOf("you")
                "third-person:singular"->setOf("he","she","it");"third-person:plural"->setOf("they")
                else->emptySet()
            }
        } else emptySet()
        val carrier=text.substring(range).lowercase()
        return side.guards.any { word -> side.windows[word].orEmpty().any { whole ->
            whole.first<=range.first && whole.last>=range.last && whole!=range &&
                subjects.none{subject->text.substring(whole).lowercase()=="$subject $carrier"}
        }}
    }
    private fun completePast(form:Form)=form.mode==4 && form.pos=="verb" && form.targetSafe &&
        !form.grammar && PAST_RULE in form.features
    private fun pastGrammar(form:Form,analyses:List<Form>,text:String,range:IntRange,language:String):Boolean {
        if(!completePast(form))return false
        if(language=="en") {
            // A present verb with the same spelling (see/saw, for example)
            // needs evidence beyond this bounded past-tense path.
            if(analyses.any{it.pos=="verb" && it.mode in 1..2 && it.head==it.key && it.head!=form.head})return false
            if(analyses.any{it.pos!="verb" && it.targetSafe} && !hasFinitePastSubject(text,range.first))return false
        }
        return "past-source-unambiguous" in form.features ||
            (language=="en" && "past-source-requires-finite-clause" in form.features && hasFinitePastSubject(text,range.first))
    }

    private fun completeNoun(form:Form)=form.pos=="noun" && form.mode in 1..2 && form.targetSafe &&
        !form.grammar && !form.proper && form.start==0 && form.end==form.written.length
    private fun completePresent(form:Form)=form.mode==5 && form.pos=="verb" && form.targetSafe &&
        (!form.grammar || form.head=="need") && PRESENT_RULE in form.features
    private fun completeVerb(form:Form,mode:Int)=if(mode==4)completePast(form) else completePresent(form)
    private fun verbKey(form:Form,mode:Int)=(if(mode==4) "@past:" else "@present:")+form.head
    private fun verbGrammar(form:Form,analyses:List<Form>,text:String,range:IntRange,language:String,mode:Int)=
        if(mode==4)pastGrammar(form,analyses,text,range,language) else completePresent(form) &&
            (!form.grammar || (language=="en" && form.head=="need" && PresentVerbGrammar.pronominalClause(text,range,language))) &&
            !(language=="en" && analyses.any{it.mode==4 && it.lexeme!=form.lexeme}) &&
            PresentVerbGrammar.people(form.features,text,range.first,language).isNotEmpty()

    private fun contextualEntries(left:Side,right:Side,db:SQLiteDatabase,original:String,translation:String,source:String,target:String,
        strict:List<VocabularyEntry>,alignment:SentenceAlignment,diagnostic:(String)->Unit,wholeMode:Int=0):List<VocabularyEntry> {
        val targetKeys=right.forms.flatMap { (word,forms) -> forms.flatMap { form ->
            if(wholeMode!=0 && !completeVerb(form,wholeMode))emptyList() else right.windows[word].orEmpty().mapNotNull { carrier -> focus(form,carrier,translation)?.let{if(wholeMode!=0) verbKey(form,wholeMode) else key(translation.substring(it))} }
        }}.toSet()
        val sourceKeys=left.forms.flatMap { (word,forms) -> forms.flatMap { form ->
            if(wholeMode!=0 && !completeVerb(form,wholeMode))emptyList() else left.windows[word].orEmpty().mapNotNull { carrier -> focus(form,carrier,original)?.let{if(wholeMode!=0) verbKey(form,wholeMode) else key(original.substring(it))} }
        }}.toSet()
        val evidence=ContextWitnessLookup.load(db,original,source,target,left.release,sourceKeys,targetKeys,left.windows.keys) ?: return emptyList()
        // Reciprocal evidence requires a separately accepted nearby vocabulary
        // anchor in both sentences. A translated context word alone is insufficient.
        val reverseEvidence=if(wholeMode==5)ContextWitnessLookup.load(db,translation,target,source,right.release,targetKeys,sourceKeys,right.windows.keys) else null
        val lexicalWindows=left.windows.filterKeys { word ->
            val forms=left.forms[word].orEmpty();val names=forms.filter{it.proper}
            (word !in left.blocked || (word in left.names && names.isNotEmpty() && names.all{it.written.firstOrNull()?.isUpperCase()==true})) &&
                forms.any{it.targetSafe} && forms.none{it.grammar}
        }.mapValues { (word,ranges) -> if(word in left.names)ranges.filter{original[it.first].isLowerCase()} else ranges }
        fun reverseWindows(focus:IntRange):Map<String,List<IntRange>> {
            if(reverseEvidence==null)return emptyMap()
            val anchors=strict.mapNotNull { e ->
                val a=e.sourceScope;val b=e.targetScope
                if(a==null || b==null || a.original!=original || b.translation!=translation)return@mapNotNull null
                val sourceRange=a.start until a.end
                if(lexicalWindows.values.none{sourceRange in it} ||
                    !evidence.hasNearbyContext(focus,original,mapOf("anchor" to listOf(sourceRange))))return@mapNotNull null
                b.start until b.end
            }.toSet()
            return right.windows.mapValues{(_,ranges)->ranges.filter{it in anchors}}.filterValues{it.isNotEmpty()}
        }
        val needsReading=target in setOf("ar","zh","ja","ko")
        data class Claim(val sourceRange:IntRange,val range:IntRange,val reading:String)
        val output=mutableListOf<VocabularyEntry>()
        for((word,forms) in left.forms) {
            // Hard grammar, truncated inventories, names and unattested stems
            // cannot become acceptable merely through frequent co-occurrence.
            val contextualNeed=wholeMode==5 && source=="en" && forms.any{completePresent(it) && it.head=="need"}
            if(word in left.targetBlocked || (forms.any{it.grammar} && !contextualNeed))continue
            for(carrier in left.windows[word].orEmpty().distinct()) {
                if(!alignment.uniqueSource(carrier,left.windows[word].orEmpty().filterNot{if(wholeMode==5)protectedPresent(left,it,original,source) else containedInKnownWord(left,it)}))continue
                val transparentSource=wholeMode==5 && containedInKnownWord(left,carrier) && !protectedPresent(left,carrier,original,source)
                if((if(wholeMode==5)protectedPresent(left,carrier,original,source) else containedInKnownWord(left,carrier)) || strict.any { e -> e.sourceScope?.let{it.start<carrier.last+1 && carrier.first<it.end}==true })continue
                val actual=original.substring(carrier)
                val lexicalNeed=contextualNeed && PresentVerbGrammar.pronominalClause(original,carrier,source)
                if(word in left.blocked && !lexicalNeed) {
                    val proper=forms.filter{it.proper}
                    // Keep explicit case evidence: lowercase "house" does not
                    // match the published surname "House". Same-case names,
                    // grammar, unknown analyses and overflow still abstain.
                    if(word !in left.names || actual.firstOrNull()?.isLowerCase()!=true || proper.isEmpty() ||
                        proper.any{it.written.firstOrNull()?.isUpperCase()!=true})continue
                }
                val usable=forms.filter{it.targetSafe && key(actual)==key(it.written) &&
                    if(wholeMode!=0) verbGrammar(it,forms,original,carrier,source,wholeMode) && targetCaseMatches(it,carrier,original)
                    else it.mode in 1..3 && targetCaseMatches(it,carrier,original)}
                // Conflicting carrier boundaries require a whole noun, a noun
                // counterpart and an explicit nearby lexical witness. Do not
                // guess an internal stem from a competing verbal analysis.
                val focuses=usable.mapNotNull { form -> focus(form,carrier,original)?.let{it to form.number} }.toSet()
                val conflictingGeometry=usable.any{it.mode==3} && focuses.size!=1
                val allMeanings=(if(wholeMode!=0) forms.filter{it.targetSafe && key(actual)==key(it.written)} else usable).flatMap{linkedTerms(left,it)}.filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                val claims=mutableSetOf<Claim>();val reverseClaims=mutableSetOf<Claim>();val pronounClaims=mutableSetOf<Claim>()
                for(form in usable) {
                    if(conflictingGeometry && (form.pos!="noun" || form.mode !in 1..2))continue
                    val sourceFocus=focus(form,carrier,original) ?: continue
                    val meanings=linkedTerms(left,form).filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                    if(meanings.isEmpty())continue
                    val anchoredReverse=reverseWindows(sourceFocus)
                    val sourcePronounClause=wholeMode==5 && PresentVerbGrammar.pronominalClause(original,sourceFocus,source)
                    val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                    for((other,targets) in right.forms) {
                        if(other in right.targetBlocked)continue
                        for(candidate in targets.distinctBy{listOf(it.lexeme,it.start,it.end,it.number,it.mode)}) {
                            val readings=readings(right,candidate,meanings)
                            if(needsReading && readings.size!=1)continue
                            if(conflictingGeometry && (candidate.pos!="noun" || candidate.grammar))continue
                            if(!candidate.targetSafe || ("abbreviation" in candidate.features && targets.any{it.grammar}) || (if(wholeMode!=0) !completeVerb(candidate,wholeMode) else candidate.mode !in 1..3) || !numberCompatible(form,candidate,source,target) ||
                                linkedTerms(right,candidate).none{it.eligible && it.sense in meanings})continue
                            val targetMeanings=linkedTerms(right,candidate).filter{it.eligible}.map{it.sense}.toSet()
                            // A grammatical cue alone cannot choose a narrower
                            // meaning while nearby lexical context is unexplained.
                            // Short grammar-only utterances retain their prior path.
                            val narrow=!targetMeanings.containsAll(allMeanings) || targets.any{it.grammar}
                            val nearbyLexical=evidence.hasNearbyContext(sourceFocus,original,lexicalWindows)
                            if((conflictingGeometry || (transparentSource && !sourcePronounClause)) && !nearbyLexical)continue
                            val cueWindows=if(conflictingGeometry || transparentSource || (narrow && nearbyLexical))lexicalWindows else left.windows
                            for(targetCarrier in right.windows[other].orEmpty().distinct()) {
                                if(wholeMode!=0 && !verbGrammar(candidate,targets,translation,targetCarrier,target,wholeMode))continue
                                if(wholeMode==5 && PresentVerbGrammar.people(form.features,original,carrier.first,source)
                                    .intersect(PresentVerbGrammar.people(candidate.features,translation,targetCarrier.first,target)).isEmpty())continue
                                val protectedTarget=protectedTarget(right,targetCarrier,translation,target,features)
                                val transparentTarget=wholeMode==5 && protectedTarget && !protectedPresent(right,targetCarrier,translation,target)
                                if((protectedTarget && !transparentTarget) || (transparentTarget && !nearbyLexical && !sourcePronounClause) || !targetCaseMatches(candidate,targetCarrier,translation))continue
                                val targetFocus=focus(candidate,targetCarrier,translation) ?: continue
                                if(!alignment.permits(sourceFocus,targetFocus))continue
                                if(strict.any { e -> e.targetScope?.let{it.start<targetFocus.last+1 && targetFocus.first<it.end}==true })continue
                                val sourceKey=if(wholeMode!=0) verbKey(form,wholeMode) else key(original.substring(sourceFocus))
                                val targetKey=if(wholeMode!=0) verbKey(candidate,wholeMode) else key(translation.substring(targetFocus))
                                val sharedMeanings=meanings.intersect(targetMeanings)
                                val pronounClause=wholeMode==5 && PresentVerbGrammar.pronominalClause(original,sourceFocus,source) &&
                                    PresentVerbGrammar.pronominalClause(translation,targetFocus,target)
                                if((transparentSource || transparentTarget) && !nearbyLexical && !pronounClause)continue
                                val selectedWindows=if(pronounClause)left.windows else if(wholeMode==5 || transparentTarget)lexicalWindows else cueWindows
                                val nounMeanings=if(wholeMode==0 && completeNoun(form) && completeNoun(candidate))sharedMeanings else emptySet()
                                val forward=evidence.supports(sourceKey,targetKey,sourceFocus,original,selectedWindows,sharedMeanings,nounMeanings)
                                val reverse=wholeMode==5 && reverseEvidence?.supports(targetKey,sourceKey,targetFocus,translation,anchoredReverse,sharedMeanings)==true
                                if(forward || reverse) {
                                    val claim=Claim(sourceFocus,targetFocus,if(needsReading)readings.single() else "")
                                    claims+=claim
                                    if(!forward && reverse)reverseClaims+=claim
                                    if(forward && pronounClause)pronounClaims+=claim
                                }
                            }
                        }
                    }
                }
                val claim=claims.singleOrNull() ?: continue
                val targetText=translation.substring(claim.range)
                if(claim in reverseClaims)diagnostic("present_reverse_candidate")
                if(claim in pronounClaims)diagnostic("present_pronominal_candidate")
                diagnostic(when(wholeMode){4->"past_context_candidate";5->"present_context_candidate";else->"context_witness_candidate"})
                output+=VocabularyEntry(original.substring(claim.sourceRange),listOf(targetText),if(needsReading)mapOf(targetText to listOf(claim.reading)) else emptyMap(),
                    sourceScope=VocabularySourceScope(original,claim.sourceRange.first,claim.sourceRange.last+1),
                    targetScope=VocabularyTargetScope(translation,claim.range.first,claim.range.last+1))
            }
        }
        return output.distinct()
    }
    fun entries(leftDB:SQLiteDatabase,rightDB:SQLiteDatabase,original:String,translation:String,source:String,target:String,witnessDB:SQLiteDatabase?=null,diagnostic:(String)->Unit={}):List<VocabularyEntry> {
        if(original.length>16384 || translation.length>32768 || source==target)return emptyList()
        try {
            val left=load(leftDB,original,source) ?: return emptyList()
            val right=load(rightDB,translation,target) ?: return emptyList()
            require(left.inventory==right.inventory && left.release==right.release) {"Dictionary releases must match"}
            val alignment=SentenceAlignment(original,translation)
            val needsReading=target in setOf("ar","zh","ja","ko")
            data class Claim(val range:IntRange,val reading:String)
            val output=mutableListOf<VocabularyEntry>()
            for((word,forms) in left.forms) {
                if(word in left.blocked) {diagnostic("source_guard");continue}
                if(forms.map{it.lexeme}.distinct().size!=1) {diagnostic("multiple_source_entries");continue}
                val usable=forms.filter{it.sourceSafe && it.mode in 1..3}.distinctBy(::shape)
                // Different number or focus analyses are not selected away by
                // whichever target happens to be present in the translation.
                if(usable.map(::shape).distinct().size!=1) {diagnostic(if(usable.isEmpty()) "source_sense_or_form" else "source_form_conflict");continue}
                val form=usable.singleOrNull() ?: continue
                // One coarse native gloss can link several distinct senses of
                // one English headword. It then needs context corroboration.
                val ambiguousFamilies=linkedTerms(left,form).filter{it.eligible && it.explicit}.groupBy{it.family}.values
                    .map{rows->rows.map{it.sense}.toSet()}.filter{it.size>1}
                if(ambiguousFamilies.isNotEmpty() && target!="en") {
                    diagnostic("linked_sense_ambiguity");continue
                }
                val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                val meanings=linkedTerms(left,form).filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                if(meanings.isEmpty()) {diagnostic("no_eligible_link");continue}
                for(carrier in left.windows[word].orEmpty().distinct()) {
                    if(!alignment.uniqueSource(carrier,left.windows[word].orEmpty().filterNot{containedInKnownWord(left,it)}))continue
                    if(containedInKnownWord(left,carrier)) {diagnostic("source_compound");continue}
                    if(!targetCaseMatches(form,carrier,original)) {diagnostic("source_case");continue}
                    val sourceFocus=focus(form,carrier,original) ?: continue
                    val claims=mutableSetOf<Claim>()
                    for((other,targets) in right.forms) {
                        if(other in right.targetBlocked)continue
                        for(candidate in targets.distinctBy{listOf(it.lexeme,it.start,it.end,it.number,it.mode)}) {
                            val readings=readings(right,candidate,meanings)
                            if(needsReading && readings.size!=1)continue
                            if(!candidate.targetSafe || ("abbreviation" in candidate.features && targets.any{it.grammar}) || candidate.mode !in 1..3 || !numberCompatible(form,candidate,source,target))continue
                            // Returning the actual English dictionary headword
                            // preserves the whole linked sense family. A narrower
                            // counterpart still requires contextual evidence.
                            val targetMeanings=linkedTerms(right,candidate).filter{it.eligible}.map{it.sense}.toSet()
                            if(ambiguousFamilies.any{!targetMeanings.containsAll(it)})continue
                            if(linkedTerms(right,candidate).none{it.eligible && it.sense in meanings})continue
                            for(targetCarrier in right.windows[other].orEmpty().distinct()) {
                                if(protectedTarget(right,targetCarrier,translation,target,features) || !targetCaseMatches(candidate,targetCarrier,translation))continue
                                val targetFocus=focus(candidate,targetCarrier,translation) ?: continue
                                if(!alignment.permits(sourceFocus,targetFocus))continue
                                claims+=Claim(targetFocus,if(needsReading)readings.single() else "")
                            }
                        }
                    }
                    val claim=claims.singleOrNull()
                    if(claim==null) {diagnostic(if(claims.isEmpty()) "no_target_claim" else "multiple_target_claims");continue}
                    diagnostic("dictionary_candidate")
                    val sourceText=original.substring(sourceFocus);val targetText=translation.substring(claim.range)
                    output+=VocabularyEntry(sourceText,listOf(targetText),
                        if(needsReading)mapOf(targetText to listOf(claim.reading)) else emptyMap(),
                        sourceScope=VocabularySourceScope(original,sourceFocus.first,sourceFocus.last+1),
                        targetScope=VocabularyTargetScope(translation,claim.range.first,claim.range.last+1))
                }
            }
            if(witnessDB!=null) {
                output+=contextualEntries(left,right,witnessDB,original,translation,source,target,output,alignment,diagnostic)
                output+=contextualEntries(left,right,witnessDB,original,translation,source,target,output,alignment,diagnostic,wholeMode=4)
                output+=contextualEntries(left,right,witnessDB,original,translation,source,target,output,alignment,diagnostic,wholeMode=5)
            }
            return output.distinct()
        } catch(_:Overflow) {diagnostic("query_overflow");return emptyList()}
    }
}

/** Person evidence for supplied complete present verbs; native UTF-16 offsets. */
internal object PresentVerbGrammar {
    // Only a short personal-pronoun clause may use grammatical context alone.
    // Unknown words, articles, adverbs, negation and auxiliaries cannot disappear
    // merely because they lack dictionary entries.
    fun pronominalClause(text:String,focus:IntRange,language:String):Boolean {
        val pronouns=when(language) {
            "en"->setOf("i","you","he","she","it","we","they","me","him","her","us","them")
            "es"->setOf("yo","tú","vos","él","ella","usted","nosotros","nosotras","vosotros","vosotras","ellos","ellas","ustedes","me","te","lo","la","le","nos","os","los","las","les","se")
            else->return false
        }
        val stops=".!?。！？;；\r\n…"
        val start=text.substring(0,focus.first).indexOfLast{it in stops}+1
        val stop=text.substring(focus.last+1).indexOfFirst{it in stops}
        val end=if(stop<0)text.length else focus.last+1+stop
        val words=LocalImmersion.words(text,language).filter{it.first>=start && it.last<end}
        return words.size in 2..4 && focus in words && words.filter{it!=focus}.all{text.substring(it).lowercase() in pronouns}
    }
    private val subjects=mapOf(
        "en" to mapOf("i" to setOf("1s"),"you" to setOf("2p","2s"),"he" to setOf("3s"),"she" to setOf("3s"),"it" to setOf("3s"),"we" to setOf("1p"),"they" to setOf("3p")),
        "de" to mapOf("ich" to setOf("1s"),"du" to setOf("2s"),"er" to setOf("3s"),"sie" to setOf("3p","3s"),"es" to setOf("3s"),"wir" to setOf("1p"),"ihr" to setOf("2p")),
        "fr" to mapOf("je" to setOf("1s"),"j'" to setOf("1s"),"j’" to setOf("1s"),"tu" to setOf("2s"),"il" to setOf("3s"),"elle" to setOf("3s"),"on" to setOf("3s"),"nous" to setOf("1p"),"vous" to setOf("2p"),"ils" to setOf("3p"),"elles" to setOf("3p")),
        "es" to mapOf("yo" to setOf("1s"),"tú" to setOf("2s"),"vos" to setOf("2s"),"él" to setOf("3s"),"ella" to setOf("3s"),"usted" to setOf("3s"),"nosotros" to setOf("1p"),"nosotras" to setOf("1p"),"vosotros" to setOf("2p"),"vosotras" to setOf("2p"),"ellos" to setOf("3p"),"ellas" to setOf("3p"),"ustedes" to setOf("3p")),
        "pt" to mapOf("eu" to setOf("1s"),"tu" to setOf("2s"),"ele" to setOf("3s"),"ela" to setOf("3s"),"você" to setOf("3s"),"nós" to setOf("1p"),"vós" to setOf("2p"),"eles" to setOf("3p"),"elas" to setOf("3p"),"vocês" to setOf("3p"))
    )
    private val nonPresentAuxiliary=Regex("""(?i)(?<![\p{L}\p{M}\p{N}_])(?:did|didn['’]t|will|won['’]t|would|wouldn['’]t|can|can['’]t|could|couldn['’]t|shall|shan['’]t|should|shouldn['’]t|may|might|must|have|has|had|am|is|are|was|were)[ \t]+$""")
    private val previous=Regex("(?<![\\p{L}\\p{M}\\p{N}_])([\\p{L}\\p{M}]+['’]?)([ \\t]*)$")
    fun people(features:Set<String>,text:String,start:Int,language:String):Set<String> {
        if(start !in 0..text.length)return emptySet()
        val people=features.filter{it.startsWith("present-person-")}.map{it.removePrefix("present-person-")}.toSet()
        val match=previous.find(text.substring(0,start))
        val word=match?.groupValues?.get(1)?.lowercase()
        if(language=="en" && match!=null) {
            val before=text.substring(0,start).substring(0,match.range.first)
            if(nonPresentAuxiliary.containsMatchIn(before))return emptySet()
        }
        val nominal=when(language) {
            "es"->setOf("el","la","los","las","un","una","unos","unas","mi","mis","tu","tus","su","sus","nuestro","nuestra","vuestro","vuestra","este","esta","ese","esa")
            "pt"->setOf("o","a","os","as","um","uma","uns","umas","meu","minha","teu","tua","seu","sua","nosso","nossa","vosso","vossa","este","esta","esse","essa")
            else->emptySet()
        }
        if(match!=null && match.groupValues[2].isNotEmpty() && word in nominal)return emptySet()
        val separated=match!=null && (match.groupValues[2].isNotEmpty() || word in setOf("j'","j’"))
        val subject=if(separated)subjects[language]?.get(word) else null
        return if(subject!=null)people.intersect(subject) else if(language in setOf("en","de","fr"))emptySet() else people
    }
}
