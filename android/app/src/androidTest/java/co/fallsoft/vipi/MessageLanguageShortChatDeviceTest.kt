package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MessageLanguageShortChatDeviceTest {
    @Test fun detectsShortContextAndRejectsBareOrProtectedText() = runBlocking {
        MessageLanguage().use { detector ->
            assertEquals("en", detector.identify("I love music."))
            assertEquals("es", detector.identify("Me gusta la música."))
            assertEquals("ja", detector.identify("音楽が好きです。"))
            assertEquals("en", detector.identify("I love music. https://example.com/music"))
            for (text in listOf("pain", "gift", "room", "https://example.com/music", "`I love music`")) {
                assertNull(text, detector.identify(text))
            }
            assertNull(detector.identify("I love 音楽."))
            assertEquals("en", detector.identify("music", requireTwoWords = false))
        }
    }
    @Test fun cancelledAndClosedRequestsDoNotPublish() = runBlocking {
        val detector = MessageLanguage()
        val job = launch { detector.identify("I love music.") }
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        detector.close()
        assertNull(detector.identify("I love music."))
    }
}
