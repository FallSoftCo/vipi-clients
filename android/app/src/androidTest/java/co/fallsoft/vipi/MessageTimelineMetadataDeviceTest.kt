package co.fallsoft.vipi

import java.time.Instant
import java.time.ZoneId
import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class MessageTimelineMetadataDeviceTest {
    @Test
    fun unchangedNativeParagraphUpdatesHiddenTimeAndDeliveryContext() {
        val instrumentation =
            androidx.test.platform.app.InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            val view = FullMessageTextView(instrumentation.targetContext)
            val original = "Keep my exact original."
            val exact = MessageTimelineMetadata.exactTime(midday, Locale.US)
            val queued = instrumentation.targetContext.getString(R.string.delivery_waiting)
            val delivered = instrumentation.targetContext.getString(R.string.delivery_delivered)
            view.bind(
                "你好。",
                original,
                listOf("你好。", original),
                android.graphics.Color.BLACK,
                "$exact · $queued",
            )
            assertEquals(
                "你好。. $exact · $queued",
                view.createAccessibilityNodeInfo().contentDescription.toString(),
            )
            view.bind(
                "你好。",
                original,
                listOf("你好。", original),
                android.graphics.Color.BLACK,
                "$exact · $delivered",
            )
            assertEquals("你好。", view.text.toString())
            assertEquals(original, view.originalMessage)
            assertEquals(
                "你好。. $exact · $delivered",
                view.createAccessibilityNodeInfo().contentDescription.toString(),
            )
        }
    }

    private val zone = ZoneId.of("America/New_York")
    private val midday = Instant.parse("2026-11-19T17:00:00Z").toEpochMilli()

    @Test
    fun gapsDaysAndFailuresKeepMeaningfulContextWithoutRepeatedRoutineLabels() {
        assertTrue(MessageTimelineMetadata.showTime(midday, null, zone))
        assertFalse(MessageTimelineMetadata.showTime(midday + 299_999, midday, zone))
        assertTrue(MessageTimelineMetadata.showTime(midday + 300_000, midday, zone))
        val midnight = Instant.parse("2026-11-20T05:00:00Z").toEpochMilli()
        assertTrue(MessageTimelineMetadata.showTime(midnight, midnight - 1, zone))
        assertTrue(MessageTimelineMetadata.showTime(midday - 1, midday, zone))
        assertFalse(MessageTimelineMetadata.showDelivery(true, "delivered", false))
        assertTrue(MessageTimelineMetadata.showDelivery(true, "delivered", true))
        assertFalse(MessageTimelineMetadata.showDelivery(false, "delivered", false))
        for (state in listOf("queued", "failed", "expired", "cancelled", "imported")) {
            assertTrue(MessageTimelineMetadata.showDelivery(true, state, false))
            assertTrue(MessageTimelineMetadata.showDelivery(false, state, false))
        }
        assertNotEquals(
            MessageTimelineMetadata.label(midday, Locale.US, midday, zone),
            MessageTimelineMetadata.label(midday, Locale.US, midnight, zone),
        )
        assertTrue(MessageTimelineMetadata.exactTime(midday, Locale.US).contains("2026"))
        val id = "m%019d-11111111-1111-4111-8111-111111111111".format(Locale.ROOT, midday)
        assertEquals(midday, MessageTimelineMetadata.botTime(id))
        assertNull(MessageTimelineMetadata.botTime("legacy-message-with-no-time"))
        assertNull(
            MessageTimelineMetadata.botTime(
                "m9999999999999999999-11111111-1111-4111-8111-111111111111"
            )
        )
    }
}
