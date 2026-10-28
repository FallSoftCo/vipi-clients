package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class ContextFrameTest {
    @Test fun attachedGrammarStaysOriginalWhileOnlyTheAssessedNounChanges() {
        data class Case(val original:String,val translation:String,val language:String,val noun:String,
            val suffix:String,val target:String,val reading:String)
        for((original,translation,language,noun,suffix,target,reading) in listOf(
            Case("책을 가져왔어요.","I brought the book.","ko","책","을","book","chaek"),
            Case("Tutakutana shuleni.","We will meet at school.","sw","shule","ni","school",""))) {
            val parts=listOf(ContextPart.Focus(noun),ContextPart.Literal(suffix))
            val frame=ContextFrame("attached", "specific noun",language,"en",parts,listOf(ContextPart.Focus(target)),targetUnit=true)
            val hit=ContextFrameHit(frame,listOf(range(original,noun+suffix)),listOf(range(translation,target)))
            val values=ContextFrameMatcher.entries(original,translation,language,"en",listOf(hit))
            val result=ImmersionEngine().align(original,translation,values,1.0,"en")
            assertEquals(listOf(noun),result.spans.map{it.original})
            assertEquals(original.replace(noun,target),result.speech(language,"en").joinToString(""){it.text})
            assertEquals(original,result.speech(language,"en",result.spans.map{it.id}.toSet()).joinToString(""){it.text})
            val reversed=ContextFrame("reverse","specific noun","en",language,listOf(ContextPart.Focus(target)),parts,reading,sourceUnit=true)
            val reverseHit=ContextFrameHit(reversed,hit.targetWindows,hit.sourceWindows)
            val reverseValues=ContextFrameMatcher.entries(translation,original,"en",language,listOf(reverseHit))
            val reverseResult=ImmersionEngine().align(translation,original,reverseValues,1.0,language)
            assertEquals(listOf(noun),reverseResult.spans.map{it.translated})
            if(language=="ko")assertEquals(reading,reverseResult.spans.single().romanization)
            val denied=hit.copy(frame=frame.copy(targetUnit=false))
            assertTrue(ContextFrameMatcher.entries(original,translation,language,"en",listOf(denied)).isEmpty())
            val wrong=hit.copy(frame=frame.copy(sourceParts=listOf(ContextPart.Focus(noun),ContextPart.Literal("wrong"))))
            assertTrue(ContextFrameMatcher.entries(original,translation,language,"en",listOf(wrong)).isEmpty())
        }
    }
    @Test fun finitePossessorsRemainOutsideFocus() {
        val parts=listOf(ContextPart.Slot(listOf("my ","your ","their ")),ContextPart.Focus("dog"))
        assertEquals(6..8,ContextMappingMatcher.focus("their dog",parts))
        assertNull(ContextMappingMatcher.focus("her dog",parts))
        assertNull(ContextMappingMatcher.focus("dog",listOf(ContextPart.Focus("dog"))))
        assertNull(ContextMappingMatcher.focus(" dog",listOf(ContextPart.Slot(listOf(" ","\n")),ContextPart.Focus("dog"))))
    }
    private val original="🙂 I am reading a book now."
    private val translation="🙂 Estoy leyendo un libro ahora. Otro libro."
    private fun range(text:String,phrase:String)=text.indexOf(phrase) until text.indexOf(phrase)+phrase.length
    private fun frame(id:String="book",meaning:String="a book being read")=ContextFrame(id,meaning,"en","es",
        listOf(ContextPart.Slot(listOf("read","reading")),ContextPart.Literal(" a "),ContextPart.Focus("book")),
        listOf(ContextPart.Literal("leyendo un "),ContextPart.Focus("libro")))
    private fun hit(value:ContextFrame=frame(),targets:List<IntRange> = listOf(range(translation,"leyendo un libro")))=
        ContextFrameHit(value,listOf(range(original,"reading a book")),targets)
    private fun entries(hits:List<ContextFrameHit>)=ContextFrameMatcher.entries(original,translation,"en","es",hits)
    @Test fun bothMatchedContextsBindOnlyTheirLexicalFocus() {
        val values=entries(listOf(hit()));assertEquals(1,values.size)
        val result=ImmersionEngine().align(original,translation,values,1.0,"es")
        assertEquals(1,result.spans.size);assertEquals("book",result.spans.single().original)
        assertEquals(translation.indexOf("libro"),result.spans.single().targetStart)
        assertEquals(listOf("libro"),result.speech("en","es").filter{it.language=="es"}.map{it.text})
    }
    @Test fun missingTargetCannotEraseAContrarySourceMeaning() {
        assertTrue(entries(listOf(hit(targets=emptyList()))).isEmpty())
        assertTrue(entries(listOf(hit(),hit(frame("rival","an unrelated sense"),emptyList()))).isEmpty())
    }
    @Test fun repeatedMatchedTargetAndOverflowAbstain() {
        val repeated="leyendo un libro y leyendo un libro"
        assertTrue(ContextFrameMatcher.entries(original,repeated,"en","es",listOf(hit(targets=listOf(0..15,19..34)))).isEmpty())
        assertTrue(entries((0..256).map{hit(frame("book-$it"))}).isEmpty())
    }
    @Test fun indexHitMustActuallyMatchTheBoundedPattern() {
        assertTrue(entries(listOf(ContextFrameHit(frame(),listOf(0..3),emptyList()))).isEmpty())
        assertTrue(entries(listOf(hit(targets=listOf(999..1003)))).isEmpty())
    }
    @Test fun completeUnitNeedsExplicitScopeAndBothUniqueNativeForms() {
        val source="I lost my phone number.";val target="Perdí mi número de teléfono."
        fun unit(approved:Boolean,id:String="phone",meaning:String="telephone contact number")=ContextFrame(id,meaning,"en","es",
            listOf(ContextPart.Focus("phone number")),listOf(ContextPart.Focus("número de teléfono")),lexicalUnit=approved)
        fun hit(value:ContextFrame,targets:List<IntRange> = listOf(range(target,"número de teléfono")))=
            ContextFrameHit(value,listOf(range(source,"phone number")),targets)
        fun result(hits:List<ContextFrameHit>)=ContextFrameMatcher.entries(source,target,"en","es",hits)
        assertTrue(result(listOf(hit(unit(false)))).isEmpty())
        val entries=result(listOf(hit(unit(true))));assertEquals(1,entries.size)
        assertEquals("phone number",ImmersionEngine().align(source,target,entries,1.0,"es").spans.single().original)
        assertTrue(result(listOf(hit(unit(true),emptyList()))).isEmpty())
        assertTrue(result(listOf(hit(unit(true)),hit(unit(true,"rival","a different meaning"),emptyList()))).isEmpty())
        val malformed=unit(true).copy(sourceParts=listOf(ContextPart.Literal("my "),ContextPart.Focus("phone number")))
        assertTrue(result(listOf(hit(malformed))).isEmpty())
    }
    @Test fun completePluralTargetKeepsItsSuffixWithoutResolvingOtherAmbiguities() {
        val source="children"; val target="子どもたち"
        fun hit(id:String,word:String,reading:String,meaning:String="human children",start:Int=0) = ContextFrameHit(
            ContextFrame(id,meaning,"en","ja",listOf(ContextPart.Focus(source)),listOf(ContextPart.Focus(word)),reading,true),
            listOf(source.indices),listOf(start until start+word.length))
        fun entries(text:String,hits:List<ContextFrameHit>)=ContextFrameMatcher.entries(source,text,"en","ja",hits)
        val short=hit("short","子ども","kodomo"); val full=hit("full",target,"kodomotachi")
        val values=entries(target,listOf(short,full))
        val result=ImmersionEngine().align(source,target,values,1.0,"ja")
        assertEquals(listOf(target),result.spans.map{it.translated})
        assertEquals("kodomotachi",result.spans.single().romanization)
        assertTrue(entries(target,listOf(short,full.copy(frame=full.frame.copy(meaning="another meaning")))).isEmpty())
        val disagree=hit("reading-conflict",target,"different")
        assertTrue(ImmersionEngine().align(source,target,entries(target,listOf(short,full,disagree)),1.0,"ja").spans.isEmpty())
        val separate="子ども 子どもたち"
        val second=hit("second",target,"kodomotachi",start=4)
        assertTrue(ImmersionEngine().align(source,separate,entries(separate,listOf(short,second)),1.0,"ja").spans.isEmpty())
        assertTrue(entries(separate,listOf(short.copy(targetWindows=listOf(0..2,4..6)),second)).isEmpty())
    }

    @Test fun commonNounCaseAliasesCannotBecomeNamesAndCannotEraseContraryEvidence() {
        fun run(original:String,target:String,sourceLanguage:String="en",flag:Boolean=true,other:ContextFrameHit?=null):List<VocabularyEntry> {
            val frame=ContextFrame("case","food",sourceLanguage,"es",listOf(ContextPart.Focus("Food")),listOf(ContextPart.Focus("comida")),
                lexicalUnit=true,commonNounCaseVariants=flag)
            val hit=ContextFrameHit(frame,listOf(range(original,"Food")),listOf(range(target,"comida")))
            return ContextFrameMatcher.entries(original,target,sourceLanguage,"es",listOfNotNull(hit,other))
        }
        assertEquals(1,run("Food is ready.","La comida está lista.").size)
        assertEquals(1,run("Done. Food is ready.","La comida está lista.").size)
        assertTrue(run("I called Food yesterday.","Llamé a la comida ayer.").isEmpty())
        assertEquals(1,run("I called Food yesterday.","Llamé a la comida ayer.",flag=false).size)
        assertEquals(1,run("Ich mag Food.","Me gusta la comida.",sourceLanguage="de").size)
        val source="Food is ready.";val translated="La comida está lista."
        val contrary=ContextFrameHit(ContextFrame("contrary","another sense","en","es",listOf(ContextPart.Focus("Food")),
            listOf(ContextPart.Focus("other")),lexicalUnit=true,commonNounCaseVariants=true),listOf(range(source,"Food")),emptyList())
        assertTrue(run(source,translated,other=contrary).isEmpty())
        val reversed=ContextFrame("reverse","food","es","en",listOf(ContextPart.Focus("comida")),listOf(ContextPart.Focus("Food")),
            lexicalUnit=true,commonNounCaseVariants=true)
        val reverseHit=ContextFrameHit(reversed,listOf(range("Llamé a la comida ayer.","comida")),listOf(range("I called Food yesterday.","Food")))
        assertTrue(ContextFrameMatcher.entries("Llamé a la comida ayer.","I called Food yesterday.","es","en",listOf(reverseHit)).isEmpty())
    }

    @Test fun openingPunctuationPreservesSentenceCaseWithoutExcusingMidSentenceNames() {
        for(text in listOf("¿Tiempo?","¡Food!","Done. “Food”","'Food'")) {
            val start=text.indexOfFirst{it=='T' || it=='F'}
            assertTrue(WrittenCase.sentenceInitial(text,start))
        }
        for(text in listOf("I called “Food”.","Dije ¿Tiempo?","Use ROOM.")) {
            val start=text.indexOfFirst{it=='F' || it=='T' || it=='R'}
            assertFalse(WrittenCase.sentenceInitial(text,start))
        }
    }

}
