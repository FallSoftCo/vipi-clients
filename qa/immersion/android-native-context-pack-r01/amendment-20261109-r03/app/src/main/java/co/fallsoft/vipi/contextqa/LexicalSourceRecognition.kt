package co.fallsoft.vipi.contextqa
import co.fallsoft.vipi.contextqa.FrozenContextTokenizer.Range

internal object LexicalSourceRecognition {
    data class Form(val lexemeID:String,val written:String,val intrinsicRange:Range?,val number:Int,val mode:Int,
        val sourceSafe:Boolean,val targetSafe:Boolean,val features:Set<String>,val partOfSpeech:String,
        val isProperName:Boolean,val isGrammar:Boolean,val headword:String)
    data class Unit(val key:String,val range:Range,val original:String,val sourceBlocked:Boolean,
        val targetBlocked:Boolean,val hasNameGuard:Boolean,val protectsInner:Boolean,val forms:List<Form>)
    data class Snapshot(val original:String,val language:String,val dictionaryRelease:String,val dictionaryInventory:String,
        val suppliedProtection:List<Range>,val namedPlaces:List<Range>,val phraseRanges:List<Range>,val units:List<Unit>) {
        fun matches(text:String,language:String,release:String,inventory:String,protection:List<Range>) =
            original==text && this.language==language && dictionaryRelease==release && dictionaryInventory==inventory && suppliedProtection==protection
        fun hasStructuralProtection(range:Range):Boolean {
            if(!valid(range,original))return true
            if((suppliedProtection+namedPlaces).any{it.start<range.end && range.start<it.end})return true
            fun contains(outer:Range)=outer!=range && outer.start<=range.start && outer.end>=range.end
            return phraseRanges.any(::contains) || units.any{it.protectsInner && contains(it.range)}
        }
    }
    fun valid(range:Range,text:String):Boolean {
        if(range.start<0 || range.end<=range.start || range.end>text.length)return false
        val edges=Regex("\\X").findAll(text).map{it.range.last+1}.toSet()+0
        return range.start in edges && range.end in edges
    }
    fun intrinsic(mode:Int,start:Int,end:Int,written:String):Range? {
        if(mode==0 && start==0 && end==0)return null
        require(start>=0 && end>start && end<=written.length)
        // Match the qualified Apple adapter's bounds contract. This is stored
        // lexical geometry, not approval to emit at this or any source range.
        return Range(start,end)
    }
}
