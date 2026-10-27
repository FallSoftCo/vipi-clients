package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ChatResponseDeviceTest {
    @Test fun shortRepliesWorkWithoutTranslationPreparation() = runBlocking {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        ConversationImmersion(context,"en","sw",0.25).use { owner ->
            assertNull(owner.ready)
            for((original,expected) in listOf("yes" to "Ndiyo.","YES" to "Ndiyo.","No." to "Hapana.","OK" to "Sawa.","Please." to "Tafadhali.")) {
                val value=requireNotNull(owner.result(original))
                assertEquals(original,value.original);assertEquals(expected,value.translation);assertEquals(1,value.spans.size)
            }
            for((original,expected) in listOf("ndio" to "Yes.","NDIO" to "Yes.","Hapana" to "No.","sawa" to "Okay.","Tafadhali." to "Please.")) {
                val value=requireNotNull(owner.result(original))
                assertEquals(expected,value.original);assertEquals(original,value.translation);assertEquals(1,value.spans.size)
            }
            assertNull("No translator/model preparation was requested",owner.ready)
        }
        val catalog=BundledImmersionCatalog(context)
        assertNull(catalog.reference("Please wait.","en","sw"))
        assertNull(catalog.reference("No.","en","zh"))
        assertNull(catalog.reference("Bitte.","de","sw"))
        assertNull(catalog.reference("Please.","en","ko"))
    }
    @Test fun chineseReadingConstructionPreservesVerbAndRejectsLargerWords() {
        val catalog=BundledImmersionCatalog(InstrumentationRegistry.getInstrumentation().targetContext)
        val forward=catalog.result("She is reading a book.","她在看书。","en","zh",1.0)
        assertEquals("She is reading a 书.",forward.speech("en","zh").joinToString(""){it.text})
        assertEquals("shū",forward.spans.single().romanization)
        val reverse=catalog.result("她在看书。","She is reading a book.","zh","en",1.0)
        assertEquals("她在看book。",reverse.speech("zh","en").joinToString(""){it.text})
        for((left,right) in listOf("看书店。" to "book.","看书。" to "read.","看书看书。" to "book."))
            assertTrue("No unqualified internal, missing or repeated focus",catalog.result(left,right,"zh","en",1.0).spans.isEmpty())
    }
    @Test fun combinedBookCarriersPreserveBothLanguagesGrammar() {
        val catalog=BundledImmersionCatalog(InstrumentationRegistry.getInstrumentation().targetContext)
        for(suffix in listOf("은","이","을","과","도","만","에","에서","의")) {
            val korean="책$suffix"
            val forward=catalog.result(korean,"看书","ko","zh",1.0)
            assertEquals(1,forward.spans.size)
            assertEquals("书$suffix",forward.speech("ko","zh").joinToString(""){it.text})
            assertEquals("shū",forward.spans.single().romanization)
            val reverse=catalog.result("看书",korean,"zh","ko",1.0)
            assertEquals(1,reverse.spans.size)
            assertEquals("看책",reverse.speech("zh","ko").joinToString(""){it.text})
            assertEquals("chaek",reverse.spans.single().romanization)
        }
        for((korean,chinese) in listOf("책방" to "看书","책을" to "看书店","책을" to "看书看书","책을 책을" to "看书","책을" to "看")) {
            assertTrue(catalog.result(korean,chinese,"ko","zh",1.0).spans.isEmpty())
            assertTrue(catalog.result(chinese,korean,"zh","ko",1.0).spans.isEmpty())
        }
    }
}
