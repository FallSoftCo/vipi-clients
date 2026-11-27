package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import java.util.UUID
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class PrivateSpeechCleanupDeviceTest {
    @get:Rule val compose = createComposeRule()

    private fun isolated(): Pair<ContextWrapper, File> {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "speech-cleanup-qa-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getApplicationContext() = this

                override fun getCacheDir() = File(root, "cache").apply { mkdirs() }

                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        return context to root
    }

    @Test
    fun logoutStopsActualPlaybackAndRemovesPrivateAudioButKeepsVoiceData(): Unit = runBlocking {
        compose.setContent {}
        val (context, root) = isolated()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val public =
            File(context.noBackupFilesDir, "speech/public-voice-control").apply {
                parentFile!!.mkdirs()
                writeText("reusable")
            }
        val speech =
            withContext(Dispatchers.Main) {
                SpeechPlayback(context, "en", scope).also {
                    it.prepare(mapOf("en" to "Hello.", "sw" to "Habari."))
                }
            }
        try {
            withTimeout(20_000) { while (speech.state != SpeechState.READY) delay(20) }
            withContext(Dispatchers.Main) {
                speech.toggle(
                    "private-message",
                    listOf(SpeechSpan("This is private message audio. ".repeat(40), "en")),
                )
            }
            withTimeout(20_000) { while (speech.state != SpeechState.PLAYING) delay(20) }
            assertTrue(
                File(context.cacheDir, "vipi-speech").walkTopDown().any { it.extension == "wav" }
            )
            withContext(Dispatchers.Main) { Authentication(context).signOutLocally() }
            assertNull(speech.activeMessage)
            assertFalse(File(context.cacheDir, "vipi-speech").exists())
            assertEquals("reusable", public.readText())
            delay(250)
            assertFalse(File(context.cacheDir, "vipi-speech").exists())
            withContext(Dispatchers.Main) {
                speech.toggle("late", listOf(SpeechSpan("Late audio", "en")))
            }
            assertNull(speech.activeMessage)
        } finally {
            withContext(Dispatchers.Main) { speech.close() }
            scope.cancel()
            root.deleteRecursively()
        }
    }

    @Test
    fun boundaryCancelsInFlightWriterAndCannotResurrectPriorDirectory(): Unit = runBlocking {
        val (context, root) = isolated()
        var invalidated = false
        val lease = PrivateSpeechCache.register(context, files = true) { invalidated = true }
        val began = CompletableDeferred<Unit>()
        val work =
            async(Dispatchers.Default) {
                lease.track {
                    lease.access { File(it, "partial.wav").writeText("private") }
                    began.complete(Unit)
                    try {
                        awaitCancellation()
                    } finally {
                        try {
                            lease.access { File(it, "late.wav").writeText("must not be written") }
                            fail("Stale writer accepted")
                        } catch (_: CancellationException) {}
                    }
                }
            }
        try {
            began.await()
            PrivateSpeechCache.erase(context)
            try {
                work.await()
                fail("Work was not cancelled")
            } catch (_: CancellationException) {}
            assertTrue(invalidated)
            assertFalse(File(context.cacheDir, "vipi-speech").exists())
            val next = PrivateSpeechCache.register(context, files = true) {}
            try {
                assertNotEquals(lease.root, next.root)
                try {
                    lease.access { File(it, "late.wav").writeText("must not be written") }
                    fail()
                } catch (_: CancellationException) {}
                assertFalse(requireNotNull(lease.root).exists())
            } finally {
                next.close()
            }
        } finally {
            work.cancel()
            lease.close()
            root.deleteRecursively()
        }
    }
}
