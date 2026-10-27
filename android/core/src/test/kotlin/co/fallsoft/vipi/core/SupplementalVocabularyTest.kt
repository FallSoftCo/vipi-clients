package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class SupplementalVocabularyTest {
    private val engine = ImmersionEngine()
    private fun scoped(text: String, translated: String, word: String, target: String,
        readings: Map<String,List<String>> = emptyMap()): VocabularyEntry {
        val a=text.indexOf(word); val b=translated.indexOf(target)
        return VocabularyEntry(word,listOf(target),readings,
            sourceScope=VocabularySourceScope(text,a,a+word.length),
            targetScope=VocabularyTargetScope(translated,b,b+target.length))
    }

    @Test fun supplementsFillGapsAndShareOneDensityBudget() {
        val text="Bring bread and milk."; val translation="Trae pan y leche."
        val primary=listOf(scoped(text,translation,"bread","pan"))
        val extra=listOf(scoped(text,translation,"milk","leche"))
        val result=engine.align(text,translation,primary,1.0,"es",supplementalEntries=extra)
        assertEquals(listOf("bread","milk"),result.spans.map{it.original})
        assertEquals("Bring pan and leche.",result.speech("en","es").joinToString(""){it.text})
        assertEquals(text,result.speech("en","es",result.spans.map{it.id}.toSet()).joinToString(""){it.text})
        assertEquals(1,engine.align(text,translation,primary,0.25,"es",supplementalEntries=extra).spans.size)
        assertTrue(engine.align(text,translation,primary,0.0,"es",supplementalEntries=extra).spans.isEmpty())
    }

    @Test fun acceptedOwnershipSurvivesCompetingSourcesTargetsAndNestedWords() {
        val text="Bring the train ticket and milk."; val translation="Trae el billete de tren y leche."
        val primary=listOf(scoped(text,translation,"train ticket","billete de tren"))
        val extra=listOf(scoped(text,translation,"train","tren"),
            scoped(text,translation,"milk","billete de tren"),
            scoped(text,translation,"train ticket","leche"),scoped(text,translation,"milk","leche"))
        val result=engine.align(text,translation,primary,1.0,"es",supplementalEntries=extra)
        assertEquals(listOf("train ticket","milk"),result.spans.map{it.original})
        assertEquals(listOf("billete de tren","leche"),result.spans.map{it.translated})
    }

    @Test fun rejectedPrimaryEvidenceAndNativeGuardsRemainEffective() {
        val text="Bring the train ticket and milk."; val translation="Trae el billete de tren y leche."
        val compound=VocabularyEntry("train ticket",emptyList(),protectInner=true)
        val unresolved=VocabularyEntry("milk",emptyList(),unresolvedNativeSenses=true)
        val result=engine.align(text,translation,listOf(compound,unresolved),1.0,"es",
            supplementalEntries=listOf(scoped(text,translation,"train","tren"),scoped(text,translation,"milk","leche")))
        assertTrue(result.spans.isEmpty())
        val collision=VocabularyEntry("bread",listOf("pan"),requiresContext=true)
        val sameTarget=scoped("bread loaf","pan","loaf","pan")
        assertTrue(engine.align("bread loaf","pan",listOf(collision),1.0,"es",supplementalEntries=listOf(sameTarget)).spans.isEmpty())
    }

    @Test fun supplementsRequireCurrentScopesAndKeepReadingAndIdentifierChecks() {
        val text="🙂 bread and milk"; val translation="🙂 パンと牛乳"
        val bread=scoped(text,translation,"bread","パン",mapOf("パン" to listOf("pan")))
        val milk=scoped(text,translation,"milk","牛乳")
        val result=engine.align(text,translation,emptyList(),1.0,"ja",supplementalEntries=listOf(bread,milk))
        assertEquals("pan",result.spans.single().romanization)
        assertEquals(3,result.spans.single().start)
        assertTrue(engine.align("Other bread",translation,emptyList(),1.0,"ja",supplementalEntries=listOf(bread)).spans.isEmpty())
        assertTrue(engine.align(text,"Different パン",emptyList(),1.0,"ja",supplementalEntries=listOf(bread)).spans.isEmpty())
        assertTrue(engine.align(text,translation,emptyList(),1.0,"ja",supplementalEntries=listOf(bread.copy(sourceScope=null))).spans.isEmpty())
        val url="https://bread.example"; val other="https://pan.example"
        assertTrue(engine.align(url,other,emptyList(),1.0,"es",supplementalEntries=listOf(scoped(url,other,"bread","pan"))).spans.isEmpty())
    }
}
