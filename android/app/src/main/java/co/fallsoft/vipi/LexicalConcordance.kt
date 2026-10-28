package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.*
import org.json.JSONTokener
import org.json.JSONArray

/** Indexed public dictionary evidence. No generated translations or stems. */
internal object LexicalConcordance {
    private val POLICIES=setOf("native-linked-analysis-concordance-2","native-linked-lexical-units-3","native-linked-lexical-units-4","native-linked-noun-carriers-5","native-linked-modern-lexemes-6","native-linked-chinese-lexical-7","native-linked-noun-gloss-articles-8","native-linked-adjective-agreement-10","native-linked-swahili-reviewed-13")
    private data class Form(val key:String,val lexeme:Long,val written:String,val start:Int,val end:Int,
        val number:Int,val mode:Int,val sourceSafe:Boolean,val targetSafe:Boolean,val features:Set<String>,val pos:String,val proper:Boolean,val grammar:Boolean)
    private data class Term(val sense:String,val reading:String,val eligible:Boolean,val explicit:Boolean,val family:String)
    private data class Side(val windows:Map<String,List<IntRange>>,val forms:Map<String,List<Form>>,
        val terms:Map<Long,List<Term>>,val blocked:Set<String>,val targetBlocked:Set<String>,val names:Set<String>,val guards:Set<String>,val inventory:String,val release:String,val namedPlaces:List<IntRange>,val phrases:List<IntRange>)
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
        db.rawQuery("SELECT key,value FROM metadata WHERE key IN ('schema','policy','language','source_inventory_sha256','release_id')",null).use { c ->
            while(c.moveToNext())metadata[c.getString(0)]=JSONTokener(c.getString(1)).nextValue() as String
        }
        val inventory=requireNotNull(metadata.remove("source_inventory_sha256"));require(inventory.matches(Regex("[0-9a-f]{64}")))
        val release=requireNotNull(metadata.remove("release_id"));require(release.matches(Regex("[0-9a-f]{64}")))
        require(metadata.remove("policy") in POLICIES)
        require(metadata==mapOf("schema" to "vipi-lexical-shard-2","language" to language))
        val raw=ReviewedFrameLookup.windows(text,language) ?: return null
        val windows=linkedMapOf<String,MutableList<IntRange>>()
        for((written,ranges) in raw)windows.getOrPut(key(written)){mutableListOf()}.addAll(ranges)
        val forms=linkedMapOf<String,MutableList<Form>>();val blocked=mutableSetOf<String>();val guards=mutableSetOf<String>();val targetBlocked=mutableSetOf<String>();val names=mutableSetOf<String>()
        var count=0
        for(batch in windows.keys.sorted().chunked(200)) {
            db.rawQuery("SELECT s.normalized,s.lexeme,s.surface,s.start,s.end,s.number,s.mode,l.source_safe,l.target_safe,s.features,l.pos,g.reason,COALESCE(g.target_blocked,0) FROM surfaces s JOIN lexemes l ON l.id=s.lexeme LEFT JOIN guards g ON g.normalized=l.normalized WHERE s.normalized IN (${marks(batch.size)}) ORDER BY s.normalized,s.lexeme",batch.toTypedArray()).use { c ->
                while(c.moveToNext()) {
                    count++;if(count>16384)throw Overflow()
                    val form=Form(c.getString(0),c.getLong(1),c.getString(2),c.getInt(3),c.getInt(4),c.getInt(5),c.getInt(6),c.getInt(7)==1,c.getInt(8)==1,JSONArray(c.getString(9)).let{a->(0 until a.length()).map{a.getString(it)}.toSet()},c.getString(10),c.getString(10) in setOf("name","proper-noun","proper_noun"),c.getString(10) in setOf("pron","det","prep","postp","conj","particle","article","aux") || c.getString(11)=="grammar" || c.getInt(12)==1)
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
        return Side(windows,forms,terms,blocked,targetBlocked,names,guards,inventory,release,namedPlaces(text,language),phrases(text,language))
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
    private fun readings(side:Side,form:Form,meanings:Set<String>):List<String> =
        side.terms[form.lexeme].orEmpty().filter{it.eligible && it.sense in meanings}
            .map{it.reading}.filter{it.isNotEmpty()}.distinct()
    private fun shape(form:Form)=listOf(
        if(form.mode==3)form.start else 0,if(form.mode==3)form.end else 0,
        form.number,if(form.mode==3)3 else 1)
    private fun focus(form:Form,range:IntRange,text:String):IntRange? {
        if(form.mode !in 1..3)return null
        if(form.mode!=3)return range
        val actual=text.substring(range)
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
        // A lexical word may be sentence-capitalized; mid-sentence capitals
        // cannot silently be reinterpreted from a lowercase dictionary entry.
        if(actual.firstOrNull()?.isUpperCase()==true && form.written.firstOrNull()?.isLowerCase()==true) {
            val before=text.substring(0,range.first).trimEnd()
            return before.isEmpty() || before.last() in ".!?。！？\n"
        }
        return actual.firstOrNull()?.isUpperCase()==form.written.firstOrNull()?.isUpperCase()
    }
    private fun containedInPhrase(side:Side,range:IntRange):Boolean = side.phrases.any{it.first<=range.first && it.last>=range.last && it!=range}
    private fun containedInKnownWord(side:Side,range:IntRange):Boolean = side.namedPlaces.any{it.first<=range.last && range.first<=it.last} || containedInPhrase(side,range) || side.guards.any { word ->
        side.windows[word].orEmpty().any { whole -> whole.first<=range.first && whole.last>=range.last && whole!=range }
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
    private fun contextualEntries(left:Side,right:Side,db:SQLiteDatabase,original:String,translation:String,source:String,target:String,
        strict:List<VocabularyEntry>,alignment:SentenceAlignment,diagnostic:(String)->Unit):List<VocabularyEntry> {
        val targetKeys=right.forms.flatMap { (word,forms) -> forms.flatMap { form ->
            right.windows[word].orEmpty().mapNotNull { carrier -> focus(form,carrier,translation)?.let{key(translation.substring(it))} }
        }}.toSet()
        val sourceKeys=left.forms.flatMap { (word,forms) -> forms.flatMap { form ->
            left.windows[word].orEmpty().mapNotNull { carrier -> focus(form,carrier,original)?.let{key(original.substring(it))} }
        }}.toSet()
        val evidence=ContextWitnessLookup.load(db,original,source,target,left.release,sourceKeys,targetKeys) ?: return emptyList()
        val lexicalWindows=left.windows.filterKeys { word ->
            val forms=left.forms[word].orEmpty();val names=forms.filter{it.proper}
            (word !in left.blocked || (word in left.names && names.isNotEmpty() && names.all{it.written.firstOrNull()?.isUpperCase()==true})) &&
                forms.any{it.targetSafe} && forms.none{it.grammar}
        }.mapValues { (word,ranges) -> if(word in left.names)ranges.filter{original[it.first].isLowerCase()} else ranges }
        val needsReading=target in setOf("ar","zh","ja","ko")
        data class Claim(val sourceRange:IntRange,val range:IntRange,val reading:String)
        val output=mutableListOf<VocabularyEntry>()
        for((word,forms) in left.forms) {
            // Hard grammar, truncated inventories, names and unattested stems
            // cannot become acceptable merely through frequent co-occurrence.
            if(word in left.targetBlocked || forms.any{it.grammar})continue
            for(carrier in left.windows[word].orEmpty().distinct()) {
                if(!alignment.uniqueSource(carrier,left.windows[word].orEmpty().filterNot{containedInKnownWord(left,it)}))continue
                if(containedInKnownWord(left,carrier) || strict.any { e -> e.sourceScope?.let{it.start<carrier.last+1 && carrier.first<it.end}==true })continue
                val actual=original.substring(carrier)
                if(word in left.blocked) {
                    val proper=forms.filter{it.proper}
                    // Keep explicit case evidence: lowercase "house" does not
                    // match the published surname "House". Same-case names,
                    // grammar, unknown analyses and overflow still abstain.
                    if(word !in left.names || actual.firstOrNull()?.isLowerCase()!=true || proper.isEmpty() ||
                        proper.any{it.written.firstOrNull()?.isUpperCase()!=true})continue
                }
                val usable=forms.filter{it.targetSafe && it.mode in 1..3 && key(actual)==key(it.written) &&
                    actual.firstOrNull()?.isUpperCase()==it.written.firstOrNull()?.isUpperCase()}
                // Conflicting carrier boundaries require a whole noun, a noun
                // counterpart and an explicit nearby lexical witness. Do not
                // guess an internal stem from a competing verbal analysis.
                val focuses=usable.mapNotNull { form -> focus(form,carrier,original)?.let{it to form.number} }.toSet()
                val conflictingGeometry=usable.any{it.mode==3} && focuses.size!=1
                val allMeanings=usable.flatMap{left.terms[it.lexeme].orEmpty()}.filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                val claims=mutableSetOf<Claim>()
                for(form in usable) {
                    if(conflictingGeometry && (form.pos!="noun" || form.mode !in 1..2))continue
                    val sourceFocus=focus(form,carrier,original) ?: continue
                    val meanings=left.terms[form.lexeme].orEmpty().filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                    if(meanings.isEmpty())continue
                    val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                    for((other,targets) in right.forms) {
                        if(other in right.targetBlocked)continue
                        for(candidate in targets.distinctBy{listOf(it.lexeme,it.start,it.end,it.number,it.mode)}) {
                            val readings=readings(right,candidate,meanings)
                            if(needsReading && readings.size!=1)continue
                            if(conflictingGeometry && (candidate.pos!="noun" || candidate.grammar))continue
                            if(!candidate.targetSafe || ("abbreviation" in candidate.features && targets.any{it.grammar}) || candidate.mode !in 1..3 || !numberCompatible(form,candidate,source,target) ||
                                right.terms[candidate.lexeme].orEmpty().none{it.eligible && it.sense in meanings})continue
                            val targetMeanings=right.terms[candidate.lexeme].orEmpty().filter{it.eligible}.map{it.sense}.toSet()
                            // A grammatical cue alone cannot choose a narrower
                            // meaning while nearby lexical context is unexplained.
                            // Short grammar-only utterances retain their prior path.
                            val narrow=!targetMeanings.containsAll(allMeanings) || targets.any{it.grammar}
                            val nearbyLexical=evidence.hasNearbyContext(sourceFocus,original,lexicalWindows)
                            if(conflictingGeometry && !nearbyLexical)continue
                            val cueWindows=if(conflictingGeometry || (narrow && nearbyLexical))lexicalWindows else left.windows
                            for(targetCarrier in right.windows[other].orEmpty().distinct()) {
                                if(protectedTarget(right,targetCarrier,translation,target,features) || !targetCaseMatches(candidate,targetCarrier,translation))continue
                                val targetFocus=focus(candidate,targetCarrier,translation) ?: continue
                                if(!alignment.permits(sourceFocus,targetFocus))continue
                                if(strict.any { e -> e.targetScope?.let{it.start<targetFocus.last+1 && targetFocus.first<it.end}==true })continue
                                if(evidence.supports(key(original.substring(sourceFocus)),key(translation.substring(targetFocus)),sourceFocus,original,cueWindows))
                                    claims+=Claim(sourceFocus,targetFocus,if(needsReading)readings.single() else "")
                            }
                        }
                    }
                }
                val claim=claims.singleOrNull() ?: continue
                val targetText=translation.substring(claim.range)
                diagnostic("context_witness_candidate")
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
                val ambiguousFamilies=left.terms[form.lexeme].orEmpty().filter{it.eligible && it.explicit}.groupBy{it.family}.values
                    .map{rows->rows.map{it.sense}.toSet()}.filter{it.size>1}
                if(ambiguousFamilies.isNotEmpty() && target!="en") {
                    diagnostic("linked_sense_ambiguity");continue
                }
                val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                val meanings=left.terms[form.lexeme].orEmpty().filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
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
                            val targetMeanings=right.terms[candidate.lexeme].orEmpty().filter{it.eligible}.map{it.sense}.toSet()
                            if(ambiguousFamilies.any{!targetMeanings.containsAll(it)})continue
                            if(right.terms[candidate.lexeme].orEmpty().none{it.eligible && it.sense in meanings})continue
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
            if(witnessDB!=null)output+=contextualEntries(left,right,witnessDB,original,translation,source,target,output,alignment,diagnostic)
            return output.distinct()
        } catch(_:Overflow) {diagnostic("query_overflow");return emptyList()}
    }
}
