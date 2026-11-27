package co.fallsoft.vipi

import java.time.LocalDate
import org.json.JSONArray
import org.json.JSONObject

/** Only local calendar dates are retained in the account's encrypted vault. */
internal class HoldEducation(private val vault: MessageVault) {
    private val key = "hold-original-days-v1"

    private fun state() =
        vault.get("local", key)?.let { JSONObject(it.toString(Charsets.UTF_8)) } ?: JSONObject()

    private fun save(data: JSONObject) = vault.put("local", key, data.toString().toByteArray())

    private fun days(data: JSONObject, field: String) = data.optJSONArray(field) ?: JSONArray()

    private fun contains(values: JSONArray, day: LocalDate) =
        (0 until values.length()).any { values.getString(it) == day.toString() }

    private fun retired(data: JSONObject) =
        data.optBoolean("dismissed") || days(data, "learned").length() >= 3

    fun hasPreviousImpression() = vault.transaction { days(state(), "shown").length() > 0 }

    fun claim(day: LocalDate): Boolean = vault.transaction {
        val data = state()
        val shown = days(data, "shown")
        if (retired(data) || contains(shown, day) || contains(days(data, "learned"), day)) false
        else if (shown.length() < 21) {
            save(data.put("shown", shown.put(day.toString())))
            true
        } else {
            val last =
                LocalDate.parse(data.optString("lastWeekly", shown.getString(shown.length() - 1)))
            if (day.isBefore(last.plusDays(7))) false
            else {
                save(data.put("lastWeekly", day.toString()))
                true
            }
        }
    }

    fun independentReveal(day: LocalDate) = vault.transaction {
        val data = state()
        val learned = days(data, "learned")
        if (!retired(data) && !contains(learned, day))
            save(data.put("learned", learned.put(day.toString())))
    }

    fun dismiss() = vault.transaction { save(state().put("dismissed", true)) }
}
