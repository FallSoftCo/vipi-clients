package co.fallsoft.vipi

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TranslationRequestDeviceTest {
    private class DelayedTranslation : LanguageTranslation {
        var started = CompletableDeferred<Unit>()
        var answer = CompletableDeferred<String>()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) {
            started.complete(Unit); answer.await()
        }
        override suspend fun translate(text: String, source: String, target: String): String {
            started.complete(Unit); return answer.await()
        }
        override fun close() = Unit
    }
    private fun main(action: () -> Unit) = InstrumentationRegistry.getInstrumentation().runOnMainSync(action)
    private fun started(provider: DelayedTranslation) = runBlocking { withTimeout(5_000) { provider.started.await() } }
    private fun finished(model: VipiModel) {
        val deadline = System.nanoTime() + 5_000_000_000
        var busy = true
        while (busy && System.nanoTime() < deadline) { main { busy = model.modelBusy }; if (busy) Thread.sleep(10) }
        assertFalse("Provider completion must settle the pending operation", busy)
    }
    private fun model(provider: DelayedTranslation): VipiModel {
        lateinit var model: VipiModel
        main { model = VipiModel(ApplicationProvider.getApplicationContext<Application>(), provider); model.navigate(Screen.LANGUAGE_DOWNLOAD) }
        return model
    }
    @Test fun editedSentenceCannotReceiveOldTranslation() {
        val provider = DelayedTranslation(); val model = model(provider)
        main { model.translate("Coffee tomorrow?") }; started(provider)
        main { model.sentenceChanged() }
        provider.answer.complete("Café mañana?"); finished(model)
        main { assertNull(model.translatedText); assertNull(model.modelMessage) }
    }
    @Test fun leavingAndReturningCannotExposePreviousSentenceResult() {
        val provider = DelayedTranslation(); val model = model(provider)
        main { model.translate("Old sentence") }; started(provider)
        main { model.navigate(Screen.SETTINGS); model.navigate(Screen.LANGUAGE_DOWNLOAD) }
        provider.answer.complete("Old result"); finished(model)
        main { assertNull(model.translatedText) }
    }
    @Test fun returningToSameLanguageDoesNotAcceptAnOldDownloadStatus() {
        val provider = DelayedTranslation(); val model = model(provider)
        var original = ""
        main { original = model.targetLanguage; model.downloadLanguage(false) }; started(provider)
        main { model.selectTarget(if (original == "fr") "de" else "fr"); model.selectTarget(original) }
        provider.answer.complete("done"); finished(model)
        main { assertNull(model.modelMessage) }
    }
    @Test fun languageChangeCannotRelabelAnOldTranslation() {
        val provider = DelayedTranslation(); val model = model(provider)
        var original = ""
        main { original = model.targetLanguage; model.translate("Coffee tomorrow?") }; started(provider)
        main { model.selectTarget(if (original == "fr") "de" else "fr"); model.selectTarget(original) }
        provider.answer.complete("Old language result"); finished(model)
        main { assertNull(model.translatedText); assertNull(model.modelMessage) }
    }
    @Test fun currentRequestAppearsAndRetryFailureClearsIt() {
        val provider = DelayedTranslation(); val model = model(provider)
        main { model.translate("Coffee tomorrow?") }; started(provider)
        provider.answer.complete("Café mañana?"); finished(model)
        main { assertEquals("Café mañana?", model.translatedText) }
        provider.started = CompletableDeferred(); provider.answer = CompletableDeferred()
        main { model.translate("New sentence"); assertNull(model.translatedText) }; started(provider)
        provider.answer.completeExceptionally(IllegalStateException("Controlled provider failure")); finished(model)
        main { assertNull(model.translatedText); assertNotNull(model.modelMessage) }
    }
    @Test fun changedIdentifierIsWithheldWithoutRewritingTheProviderResponse() {
        val provider = DelayedTranslation(); val model = model(provider)
        main { model.translate("Open https://example.test/Case") }; started(provider)
        provider.answer.complete("Abrir https://example.test/case"); finished(model)
        main { assertNull(model.translatedText); assertEquals("Translation isn’t available for this message. Your original is unchanged.", model.modelMessage) }
    }
}
