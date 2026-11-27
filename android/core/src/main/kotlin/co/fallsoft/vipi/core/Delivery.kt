package co.fallsoft.vipi.core

import java.time.Duration
import java.time.Instant
import java.util.UUID

enum class DeliveryState {
    QUEUED,
    ACCEPTED,
    DELIVERED,
    FAILED,
    EXPIRED,
}

data class DeliveryWindow(val messageID: UUID = UUID.randomUUID(), val createdAt: Instant) {
    val expiresAt: Instant
        get() = createdAt.plus(Duration.ofHours(72))

    fun canRetry(now: Instant, state: DeliveryState) =
        now < expiresAt && (state == DeliveryState.QUEUED || state == DeliveryState.ACCEPTED)
}
