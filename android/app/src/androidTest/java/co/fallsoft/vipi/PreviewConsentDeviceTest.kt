package co.fallsoft.vipi

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import kotlinx.coroutines.awaitCancellation
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

class PreviewConsentDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun receivedSnapshotIsOfflineAndEditingCancelsExplicitSenderFetch() {
        val draft = MessageActionDraft(null, ConversationRef.Direct(UUID.randomUUID()))
        val first = "https://example.com/first"
        val second = "https://example.com/second"
        val text = mutableStateOf(first)
        val requests = AtomicInteger()
        val cancelled = AtomicInteger()
        compose.setContent { MaterialTheme { Column {
            SnapshotCard(LinkSnapshot("https://example.com/received", "Offline recipient snapshot"))
            ActionComposer(draft, text.value, false, { "Maya" }) { url ->
                requests.incrementAndGet()
                if (url == first) try { awaitCancellation() } finally { cancelled.incrementAndGet() }
                else LinkSnapshot(url, "Sender snapshot")
            }
        } } }
        compose.onNodeWithText("Offline recipient snapshot").assertIsDisplayed()
        assertEquals(0, requests.get())
        compose.onNodeWithText("Add preview").performClick()
        compose.waitUntil { requests.get() == 1 }
        compose.runOnIdle { text.value = second }
        compose.waitUntil { cancelled.get() == 1 }
        assertNull(draft.features.preview)
        compose.onNodeWithText("Add preview").performClick()
        compose.onNodeWithText("Sender snapshot").assertIsDisplayed()
        assertEquals(second, draft.features.preview?.url)
        compose.onNodeWithContentDescription("Remove link preview").performClick()
        assertEquals(2, requests.get())
        assertNull(draft.features.preview)
    }
}
