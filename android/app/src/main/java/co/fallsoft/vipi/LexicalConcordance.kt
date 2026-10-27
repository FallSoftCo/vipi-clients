package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.*
import org.json.JSONTokener
import org.json.JSONArray

/** Indexed public dictionary evidence. No generated translations or stems. */
internal object LexicalConcordance {
    private val POLICIES=setOf("native-linked-analysis-concordance-2","native-linked-lexical-units-3","native-linked-lexical-units-4")
    private data class Form(val key:String,val lexeme:Long,val written:String,val start:Int,val end:Int,
        val number:Int,val mode:Int,val sourceSafe:Boolean,val targetSafe:Boolean,val features:Set<String>,val proper:Boolean,val grammar:Boolean)
    private data class Term(val sense:String,val reading:String,val eligible:Boolean,val explicit:Boolean)
    private data class Side(val windows:Map<String,List<IntRange>>,val forms:Map<String,List<Form>>,
        val terms:Map<Long,List<Term>>,val blocked:Set<String>,val targetBlocked:Set<String>,val names:Set<String>,val guards:Set<String>,val inventory:String,val release:String)
    private class Overflow:Exception()
    private fun key(value:String)=ImmersionEngine.lookupKey(value)
    private fun marks(count:Int)=List(count){"?"}.joinToString(",")
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
                    val form=Form(c.getString(0),c.getLong(1),c.getString(2),c.getInt(3),c.getInt(4),c.getInt(5),c.getInt(6),c.getInt(7)==1,c.getInt(8)==1,JSONArray(c.getString(9)).let{a->(0 until a.length()).map{a.getString(it)}.toSet()},c.getString(10) in setOf("name","proper-noun","proper_noun"),c.getString(10) in setOf("pron","det","prep","postp","conj","particle","article","aux") || c.getString(11)=="grammar" || c.getInt(12)==1)
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
            db.rawQuery("SELECT t.lexeme,t.sense,t.reading,t.eligible,s.explicit FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme IN (${marks(batch.size)}) ORDER BY t.lexeme,t.sense,t.reading",batch.map{it.toString()}.toTypedArray()).use { c ->
                while(c.moveToNext()) {
                    count++;if(count>32768)throw Overflow()
                    terms.getOrPut(c.getLong(0)){mutableListOf()}.add(Term(c.getString(1),c.getString(2),c.getInt(3)==1,c.getInt(4)==1))
                }
            }
        }
        return Side(windows,forms,terms,blocked,targetBlocked,names,guards,inventory,release)
    }
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
    private fun containedInKnownWord(side:Side,range:IntRange):Boolean = side.guards.any { word ->
        side.windows[word].orEmpty().any { whole -> whole.first<=range.first && whole.last>=range.last && whole!=range }
    }
    private fun protectedTarget(side:Side,range:IntRange,text:String,language:String,features:Set<String>):Boolean {
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
        strict:List<VocabularyEntry>,diagnostic:(String)->Unit):List<VocabularyEntry> {
        val targetKeys=right.forms.flatMap { (word,forms) -> forms.flatMap { form ->
            right.windows[word].orEmpty().mapNotNull { carrier -> focus(form,carrier,translation)?.let{key(translation.substring(it))} }
        }}.toSet()
        val evidence=ContextWitnessLookup.load(db,original,source,target,left.release,left.forms.keys,targetKeys) ?: return emptyList()
        val needsReading=target in setOf("ar","zh","ja","ko")
        data class Claim(val range:IntRange,val reading:String)
        val output=mutableListOf<VocabularyEntry>()
        for((word,forms) in left.forms) {
            // Hard grammar, truncated inventories, names and unattested stems
            // cannot become acceptable merely through frequent co-occurrence.
            if(word in left.targetBlocked || forms.any{it.grammar})continue
            for(carrier in left.windows[word].orEmpty().distinct()) {
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
                val usable=forms.filter{it.targetSafe && it.mode in 1..2 && key(actual)==key(it.written) &&
                    actual.firstOrNull()?.isUpperCase()==it.written.firstOrNull()?.isUpperCase()}
                val claims=mutableSetOf<Claim>()
                for(form in usable) {
                    val meanings=left.terms[form.lexeme].orEmpty().filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                    if(meanings.isEmpty())continue
                    val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                    for((other,targets) in right.forms) {
                        if(other in right.targetBlocked)continue
                        val readings=targets.flatMap{right.terms[it.lexeme].orEmpty()}.map{it.reading}.filter{it.isNotEmpty()}.distinct()
                        if(needsReading && readings.size!=1)continue
                        for(candidate in targets.distinctBy{listOf(it.lexeme,it.start,it.end,it.number,it.mode)}) {
                            if(!candidate.targetSafe || candidate.mode !in 1..3 || candidate.number!=form.number ||
                                right.terms[candidate.lexeme].orEmpty().none{it.eligible && it.sense in meanings})continue
                            for(targetCarrier in right.windows[other].orEmpty().distinct()) {
                                if(protectedTarget(right,targetCarrier,translation,target,features) || !targetCaseMatches(candidate,targetCarrier,translation))continue
                                val targetFocus=focus(candidate,targetCarrier,translation) ?: continue
                                if(strict.any { e -> e.targetScope?.let{it.start<targetFocus.last+1 && targetFocus.first<it.end}==true })continue
                                if(evidence.supports(key(actual),key(translation.substring(targetFocus)),carrier,original,left.windows))
                                    claims+=Claim(targetFocus,if(needsReading)readings.single() else "")
                            }
                        }
                    }
                }
                val claim=claims.singleOrNull() ?: continue
                val targetText=translation.substring(claim.range)
                diagnostic("context_witness_candidate")
                output+=VocabularyEntry(actual,listOf(targetText),if(needsReading)mapOf(targetText to listOf(claim.reading)) else emptyMap(),
                    sourceScope=VocabularySourceScope(original,carrier.first,carrier.last+1),
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
                val features=forms.filter{it.lexeme==form.lexeme && it.mode==form.mode}.map{it.features}.reduce{a,b->a.intersect(b)}
                val meanings=left.terms[form.lexeme].orEmpty().filter{it.eligible && (source=="en" || target=="en" || it.explicit)}.map{it.sense}.toSet()
                if(meanings.isEmpty()) {diagnostic("no_eligible_link");continue}
                for(carrier in left.windows[word].orEmpty().distinct()) {
                    if(containedInKnownWord(left,carrier)) {diagnostic("source_compound");continue}
                    val sourceFocus=focus(form,carrier,original) ?: continue
                    val claims=mutableSetOf<Claim>()
                    for((other,targets) in right.forms) {
                        if(other in right.targetBlocked)continue
                        // All dictionary readings for a written target remain
                        // evidence, including senses without a usable link.
                        val readings=targets.flatMap{right.terms[it.lexeme].orEmpty()}.map{it.reading}.filter{it.isNotEmpty()}.distinct()
                        if(needsReading && readings.size!=1)continue
                        for(candidate in targets.distinctBy{listOf(it.lexeme,it.start,it.end,it.number,it.mode)}) {
                            if(!candidate.targetSafe || candidate.mode !in 1..3 || candidate.number!=form.number)continue
                            if(right.terms[candidate.lexeme].orEmpty().none{it.eligible && it.sense in meanings})continue
                            for(targetCarrier in right.windows[other].orEmpty().distinct()) {
                                if(protectedTarget(right,targetCarrier,translation,target,features) || !targetCaseMatches(candidate,targetCarrier,translation))continue
                                val targetFocus=focus(candidate,targetCarrier,translation) ?: continue
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
            if(witnessDB!=null)output+=contextualEntries(left,right,witnessDB,original,translation,source,target,output,diagnostic)
            return output.distinct()
        } catch(_:Overflow) {diagnostic("query_overflow");return emptyList()}
    }
}
