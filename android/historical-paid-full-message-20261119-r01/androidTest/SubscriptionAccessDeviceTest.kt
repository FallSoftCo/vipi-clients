package co.fallsoft.vipi

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class SubscriptionAccessDeviceTest {
    private fun plan(active: Boolean = true, expires: String? = "2099-01-01T00:00:00Z", trial: String? = null) =
        JSONObject().put("active", active).put("expires_at", expires ?: JSONObject.NULL).put("trial_ends_at", trial ?: JSONObject.NULL)
    private fun snapshot(base: JSONObject = plan(), bot: JSONObject = plan(), available: Boolean = true) = JSONObject()
        .put("base", base).put("bot_mini", bot.put("available", available)).put("billing_account_id", "a".repeat(64)).put("server_time", Instant.now().toString())

    @Test fun expiredOrRevokedEntitlementsNeverOpenAccess() {
        val expired = PlanAccess.parse(plan(expires = "2020-01-01T00:00:00Z"))
        assertFalse(expired.usable(Instant.parse("2020-01-01T00:00:00Z")))
        assertFalse(PlanAccess.parse(plan(active = false)).usable())
        assertFalse(PlanAccess.parse(plan(expires = null)).usable())
        assertTrue(PlanAccess.parse(plan()).usable())
    }

    @Test fun paidBotCannotHideInactiveBaseOrServerRestriction() {
        val noBase = SubscriptionAccess.parse(snapshot(base = plan(active = false)))
        assertTrue(noBase.bot.usable())
        assertFalse(noBase.active(SubscriptionPlan.BOT_MINI))
        val restricted = SubscriptionAccess.parse(snapshot(available = false))
        assertTrue(restricted.active(SubscriptionPlan.BASE))
        assertFalse(restricted.active(SubscriptionPlan.BOT_MINI))
        assertTrue(SubscriptionAccess.parse(snapshot()).active(SubscriptionPlan.BOT_MINI))
    }

    @Test fun unknownTrialRemainsUnknownAndMalformedProofFailsClosed() {
        assertNull(PlanAccess.parse(plan()).trialEndsAt)
        assertTrue(runCatching { PlanAccess.parse(plan(expires = "invalid")) }.isFailure)
        assertTrue(runCatching { PlanAccess.parse(plan(expires = "2099-01-01T00:00:00Z", trial = "2099-02-01T00:00:00Z")) }.isFailure)
        assertTrue(runCatching { SubscriptionAccess.parse(snapshot().put("billing_account_id", "email@example.test")) }.isFailure)
        assertTrue(runCatching { SubscriptionAccess.parse(snapshot().put("billing_account_id", JSONObject.NULL)) }.isFailure)
    }
    @Test fun cardlessBoundaryAndMissingClockFailClosed() {
        val start = Instant.parse("2026-11-17T00:00:00Z")
        val end = start.plusSeconds(30L * 24 * 60 * 60)
        val period = JSONObject().put("started_at", start.toString()).put("ends_at", end.toString()).put("active", true)
        val base = plan(expires = end.toString(), trial = end.toString()).put("access_source", "cardless_trial").put("cardless_trial", period)
        val value = PlanAccess.parse(base)
        assertTrue(value.usable(end.minusMillis(1)))
        assertFalse(value.usable(end))
        assertTrue(runCatching { PlanAccess.parse(JSONObject(base.toString()).put("cardless_trial", JSONObject.NULL)) }.isFailure)
        val missing = snapshot().apply { remove("server_time") }
        assertFalse(SubscriptionAccess.parse(missing).active(SubscriptionPlan.BASE))
        assertTrue(runCatching { PlanAccess.parse(plan().put("verification_unavailable", "invalid")) }.isFailure)
    }

}
