package co.fallsoft.vipi

import java.text.DateFormat
import java.time.Instant
import java.time.ZoneId
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Presentation only. Exact per-message times remain available to accessibility. */
internal object MessageTimelineMetadata {
    fun showTime(time: Long, previous: Long?, zone: ZoneId = ZoneId.systemDefault()): Boolean =
        previous == null || time < previous || time - previous >= 5 * 60_000L ||
            Instant.ofEpochMilli(time).atZone(zone).toLocalDate() != Instant.ofEpochMilli(previous).atZone(zone).toLocalDate()

    fun showDelivery(outgoing: Boolean, state: String, newestOutgoing: Boolean): Boolean =
        state !in setOf("accepted", "delivered") || outgoing && newestOutgoing

    /** BotSession stores this timestamp as part of its durable ordered key.
     * Unknown legacy IDs have no fabricated date or replacement with 'now'. */
    fun botTime(id: String): Long? = if (id.matches(Regex("m[0-9]{19}-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")))
        id.substring(1, 20).toLongOrNull() else null

    fun label(time: Long, locale: Locale, now: Long = System.currentTimeMillis(), zone: ZoneId = ZoneId.systemDefault()): String {
        val olderDay = Instant.ofEpochMilli(time).atZone(zone).toLocalDate() != Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
        val format = if (olderDay) DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, locale)
            else DateFormat.getTimeInstance(DateFormat.SHORT, locale)
        format.timeZone = TimeZone.getTimeZone(zone)
        return format.format(Date(time))
    }
    fun exactTime(time: Long, locale: Locale): String =
        DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.MEDIUM, locale).format(Date(time))
}
