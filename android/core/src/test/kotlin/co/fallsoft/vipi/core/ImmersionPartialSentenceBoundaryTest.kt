package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Native-discovered projection regression, with explicit synthetic unit costs.
 * No native tokenizer/provider, independent meanings or clipboard run here.
 */
class ImmersionPartialSentenceBoundaryTest {
    private val text = "你好。下周见。未知。"
    private fun partial(original: String = text, target: String = "en", density: Double = 1.0): PartialImmersionResult {
        val second = original.indexOf("下周见。")
        val ja = target == "ja"
        return requireNotNull(SourceReferencePresentation.create(original,target,listOf(
            SourceReferenceUnit(0,3,"你好。",if(ja)"こんにちは。" else "Hello.",if(ja)"konnichiwa." else null,"development-catalog-unit-1","a".repeat(64),1),
            SourceReferenceUnit(second,second+4,"下周见。",if(ja)"また来週。" else "See you next week.",if(ja)"mata raishuu." else null,"development-catalog-unit-2","a".repeat(64),2)
        ),density,4))
    }
    @Test fun actualPublishedProjectionAtDefaultAndFullDensityKeepsUnknownTailExact() {
        val low=partial(density=.25);assertEquals(1,low.spans.size)
        assertEquals("Hello.下周见。未知。",ImmersionText.project(low))
        val full=partial();assertEquals(2,full.spans.size)
        assertEquals("Hello. See you next week.未知。",ImmersionText.project(full))
        assertNull(full.translation);assertEquals(text,full.original)
        assertEquals(listOf(0 to 3,3 to 7),full.spans.map {it.start to it.end})
        assertEquals(listOf(0 to 6,0 to 18),full.spans.map {it.targetStart to it.targetEnd})
    }
    @Test fun allAndMixedOriginalFacesUseExactSelectedFacesAndAllOriginalIsByteExact() {
        val p=partial();val left=p.spans[0].id;val right=p.spans[1].id
        assertEquals("你好。 See you next week.未知。",ImmersionText.project(p,setOf(left)))
        assertEquals("Hello. 下周见。未知。",ImmersionText.project(p,setOf(right)))
        assertEquals(text,ImmersionText.project(p,setOf(left,right)))
        assertEquals(text.toByteArray().toList(),ImmersionText.project(p,setOf(left,right)).toByteArray().toList())
    }
    @Test fun targetScriptAndReadingModesHaveExplicitDistinctSentencePolicies() {
        val p=partial(target="ja")
        assertEquals("konnichiwa. mata raishuu.未知。",ImmersionText.project(p))
        assertEquals("こんにちは。また来週。未知。",ImmersionText.project(p,showScript=true))
        assertEquals("你好。また来週。未知。",ImmersionText.project(p,setOf(0),showScript=true))
        assertEquals(text,ImmersionText.project(p,p.spans.map {it.id}.toSet(),showScript=true))
        // At least one imported reading uses sentence word spacing, not a guessed target language.
        assertEquals("你好。 mata raishuu.未知。",ImmersionText.project(p,setOf(0)))
    }
    @Test fun existingGapsPunctuationAndUnknownUnitsAreNeverReplacedBySeparatorPolicy() {
        for(gap in listOf(" ","  ","\t","\n",",","、","?!","未知。")) {
            val original="你好。"+gap+"下周见。未知。";val p=partial(original)
            assertEquals("Hello."+gap+"See you next week.未知。",ImmersionText.project(p))
            assertEquals(original,ImmersionText.project(p,p.spans.map {it.id}.toSet()))
        }
    }
    @Test fun ordinaryTouchingWordSlotsDoNotGainASentencePolicy() {
        val base=partial()
        val ordinary=ImmersionResult(base.original,"unused-synthetic-full",base.spans)
        assertEquals("Hello.See you next week.未知。",ImmersionText.project(ordinary))
        // Existing C1 Latin-letter word-slot spacing is unchanged.
        val words=ImmersionResult("甲乙","unused",listOf(ImmersionSpan(0,1,"甲","hello",0,5),ImmersionSpan(1,2,"乙","world",5,10)))
        assertEquals("hello world",ImmersionText.project(words))
    }
    @Test fun selectionUsesAtomicImportedFacesButNeverPrefixesAPartialOriginalFace() {
        val p=partial();val second=p.spans[1]
        assertEquals("See you next week.",ImmersionText.project(p,start=second.start,end=second.end))
        assertEquals("下周见。",ImmersionText.project(p,setOf(second.id),start=second.start,end=second.end))
        assertEquals("Hello. See you next week.",ImmersionText.project(p,start=1,end=6))
        assertEquals("好。See you next week.",ImmersionText.project(p,setOf(0),start=1,end=7))
        assertEquals("Hello.下周",ImmersionText.project(p,setOf(second.id),start=0,end=5))
        assertEquals("",ImmersionText.project(p,start=3,end=3))
    }
    @Test fun separatelySuppliedFullTargetAndReferenceCoordinatesNeverChange() {
        val p=partial();val provided="Hi. See you next week. Unknown."
        val withFull=p.copy(completeTranslation=provided)
        assertEquals("Hello. See you next week.未知。",ImmersionText.project(withFull))
        assertEquals(provided,withFull.translation);assertEquals(p.spans,withFull.spans);assertEquals(p.references,withFull.references)
    }
    @Test fun explicitPartialTargetMetadataRejectsCrossDirectionStructuralProof() {
        val p=partial();assertTrue(SourceReferencePresentation.isAnchored(p,"en"))
        assertFalse(SourceReferencePresentation.isAnchored(p,"es"))
    }
}
