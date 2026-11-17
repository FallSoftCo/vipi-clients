package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class ManualTranslationDeviceTest {
    @Test fun arbitrarySelectionNeedsNoImmersionWordsAndUsesActualLiveReading(): Unit=runBlocking(Dispatchers.Default) {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        var calls=0
        val translator=object:LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean) { error("unexpected download") }
            override suspend fun translate(text:String,source:String,target:String):String {calls++;assertEquals("The marmot hums.",text);return "音乐"}
            override fun close(){}
        }
        val owner=ConversationImmersion(context,"en","zh",0.0,translator=translator,qaModelsReady=true,sourceLookup=null)
        try {
            val request=owner.makeManualRequest("message","The marmot hums.",4,10,1)
            val first=owner.manualTranslation(request)
            assertEquals(ManualTranslationStatus.READY,first.status)
            assertEquals("marmot",first.result?.originalSlice)
            assertEquals("The marmot hums.",first.result?.sourceContextText)
            assertTrue(first.result?.contextExpanded==true)
            assertEquals(0,first.result?.sourceContextStartUTF16)
            assertEquals(16,first.result?.sourceContextEndUTF16)
            assertEquals("音乐",first.result?.targetText)
            assertEquals("yīnyuè",first.result?.reading?.text)
            assertEquals("zh",first.result?.targetLanguage)
            assertEquals(request,first.result?.request)
            assertNull(owner.lastOutcome)
            assertEquals("unmeasured",owner.lexicalPreparation)
            assertEquals(ManualTranslationStatus.READY,owner.manualTranslation(owner.makeManualRequest("message","The marmot hums.",4,10,2)).status)
            assertEquals(1,calls)
            owner.selectInputLanguage("message","en")
            assertEquals(ManualTranslationStatus.STALE,owner.manualTranslation(request).status)
        } finally {owner.close()}
    }

    @Test fun laterSelectionAndOwnerCloseRejectLateNativeCompletion(): Unit=runBlocking(Dispatchers.Default) {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val started=CompletableDeferred<Unit>();val release=CompletableDeferred<Unit>()
        val translator=object:LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean) {error("unexpected download")}
            override suspend fun translate(text:String,source:String,target:String):String {if(text=="first"){started.complete(Unit);release.await()};return "音乐"}
            override fun close(){}
        }
        val owner=ConversationImmersion(context,"en","zh",0.0,translator=translator,qaModelsReady=true,sourceLookup=null)
        try {
            val first=async {owner.manualTranslation(owner.makeManualRequest("message","first",0,5,1))}
            started.await()
            val second=async(start=CoroutineStart.UNDISPATCHED) {owner.manualTranslation(owner.makeManualRequest("message","second",0,6,2))}
            yield();release.complete(Unit)
            assertEquals(ManualTranslationStatus.STALE,first.await().status)
            assertEquals(ManualTranslationStatus.READY,second.await().status)
            val request=owner.makeManualRequest("message","third",0,5,3)
            owner.close()
            assertEquals(ManualTranslationStatus.STALE,owner.manualTranslation(request).status)
        } finally {release.complete(Unit);owner.close()}
    }
}
