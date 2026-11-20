package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CopyOnWriteArrayList

/** Preview input/direction proof with a controlled translator, not SDK inference. */
class OnboardingPreviewSourceDeviceTest {
    @Test fun authoredExamplePinsKnownLanguageBeforeAnyModelRequest() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals(com.google.mlkit.nl.translate.TranslateLanguage.getAllLanguages().toSet(), OnboardingPreviewSource.languages)
        assertTrue(OnboardingPreviewSource.languages.containsAll(initialLanguages.map { it.code }))
        for (source in OnboardingPreviewSource.languages) {
            val target = if (source == "en") "zh" else "en"
            val prepares = CopyOnWriteArrayList<Pair<String,String>>()
            val calls = CopyOnWriteArrayList<Triple<String,String,String>>()
            val model = object : LanguageTranslation {
                override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean) {
                    prepares += source to target
                }
                override suspend fun translate(text:String,source:String,target:String):String {
                    calls += Triple(text,source,target)
                    return "A complete controlled practice example."
                }
                override fun close() = Unit
            }
            val original = OnboardingPreviewSource.text(source)
            assertTrue(original.isNotBlank())
            OnboardingPreviewSource.translation(context,source,target,model).use { owner ->
                val value = owner.resolve("preview-$source-$target",original)
                assertEquals(original,value.original)
                assertEquals(original,value.meaningText)
                assertEquals(source,value.inputLanguage)
                assertEquals(target,value.practiceLanguage)
                assertEquals("A complete controlled practice example.",value.practiceText)
                assertTrue("Pair prepared before completion",prepares.isNotEmpty())
                assertEquals(setOf(source to target),prepares.toSet())
                assertEquals(listOf(Triple(original,source,target)),calls.toList())
            }
        }
    }
}
