package co.fallsoft.vipi.core

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class DeliveryWindowTest {
    @Test fun expiresAtOriginalSeventyTwoHours() {
        val sent = Instant.ofEpochSecond(1_000_000)
        val window = DeliveryWindow(createdAt = sent)
        assertTrue(window.canRetry(sent.plusSeconds(259_199), DeliveryState.ACCEPTED))
        assertFalse(window.canRetry(sent.plusSeconds(259_200), DeliveryState.QUEUED))
        assertFalse(window.canRetry(sent, DeliveryState.DELIVERED))
    }
}
