package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LanguageDownloadsDeviceTest {
    private class Store : LanguageDownloadStore {
        var present = setOf<String>()
        var observed: CompletableDeferred<Set<String>>? = null
        var removal: CompletableDeferred<Unit>? = null
        var started = CompletableDeferred<Unit>()
        var failDownload = false
        var lastCellular: Boolean? = null
        var calls = 0
        override suspend fun installed(pair: DownloadPair): Set<String> { calls++; return observed?.await() ?: present.intersect(pair.models) }
        override suspend fun download(pair: DownloadPair, cellular: Boolean) {
            lastCellular = cellular
            if (failDownload) { present = setOf(pair.target); throw IllegalStateException("Controlled interrupted download") }
            present = pair.models
        }
        override suspend fun remove(pair: DownloadPair) { started.complete(Unit); removal?.await(); present = present - pair.models }
        override fun close() = Unit
    }
    @Test fun readinessComesFromInstalledModelsAndFailureCanRecover() = runBlocking {
        withContext(Dispatchers.Main) {
            val store = Store(); val owner = LanguageDownloads(store); val pair = DownloadPair("es", "sw")
            owner.refresh(pair); assertFalse(owner.ready)
            store.failDownload = true; owner.download(false)
            assertEquals(false, store.lastCellular); assertEquals(setOf("sw"), owner.installed)
            assertFalse(owner.ready); assertNotNull(owner.message); assertFalse(owner.busy)
            store.failDownload = false; owner.download(true)
            assertEquals(true, store.lastCellular); assertTrue(owner.ready); assertNull(owner.message)
            owner.remove(); assertEquals(emptySet<String>(), owner.installed); assertFalse(owner.ready)
            owner.close()
        }
    }
    @Test fun staleChecksAndRemovalsCannotOverwriteAnotherVisitOrPair() = runBlocking {
        withContext(Dispatchers.Main) {
            val store = Store(); val owner = LanguageDownloads(store)
            val oldCheck = CompletableDeferred<Set<String>>(); store.observed = oldCheck
            val check = launch { owner.refresh(DownloadPair("en", "es")) }; yield()
            owner.invalidate(); store.observed = null; store.present = setOf("sw")
            owner.refresh(DownloadPair("en", "sw")); assertTrue(owner.ready)
            oldCheck.complete(setOf("es")); check.join()
            assertEquals(setOf("sw"), owner.installed)
            store.removal = CompletableDeferred()
            val removal = launch { owner.remove() }; store.started.await()
            owner.invalidate(); owner.refresh(DownloadPair("en", "ja"))
            store.removal!!.complete(Unit); removal.join()
            assertEquals(DownloadPair("en", "ja"), owner.pair); assertEquals(emptySet<String>(), owner.installed)
            assertFalse(owner.busy); assertNull(owner.message); owner.close()
        }
    }
    @Test fun invalidPairsNeverCallProviderAndClosedOwnerIgnoresCompletion() = runBlocking {
        withContext(Dispatchers.Main) {
            val store = Store(); val owner = LanguageDownloads(store)
            owner.refresh(DownloadPair("sw", "sw")); owner.download(false); owner.remove()
            assertEquals(0, store.calls); assertNotNull(owner.message)
            store.observed = CompletableDeferred()
            val check = launch { owner.refresh(DownloadPair("en", "sw")) }; yield()
            owner.close(); store.observed!!.complete(setOf("sw")); check.join()
            assertNull(owner.installed); assertFalse(owner.checking); assertFalse(owner.busy)
        }
    }
    @Test fun nativeInstalledPairAndNavigationReturnAreVerified() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        NativeLanguageDownloadStore().use { store ->
            assertEquals(setOf("sw"), store.installed(DownloadPair("en", "sw")))
            assertEquals(setOf("es", "sw"), store.installed(DownloadPair("es", "sw")))
        }
        withContext(Dispatchers.Main) {
            val app = androidx.test.core.app.ApplicationProvider.getApplicationContext<android.app.Application>()
            val model = VipiModel(app)
            model.navigate(Screen.CONVERSATION); model.navigate(Screen.LANGUAGE_DOWNLOAD); model.back()
            assertEquals(Screen.CONVERSATION, model.screen)
            model.navigate(Screen.SETTINGS); model.navigate(Screen.LANGUAGE_DOWNLOAD); model.back()
            assertEquals(Screen.SETTINGS, model.screen)
        }
    }
}
