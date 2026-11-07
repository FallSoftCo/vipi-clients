package co.fallsoft.vipi

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class SubscriptionAccessDeviceTest {
    private fun plan(active: Boolean = true, expires: String? = "2099-01-01T00:00:00Z", trial: String? = null) =
        JSONObject().put("active", active).put("expires_at", expires ?: JSONObject.NULL).put("trial_ends_at", trial ?: JSONObject.NULL)
    private fun snapshot(base: JSONObject = plan(), bot: JSONObject = plan(), available: Boolean = true) = JSONObject()
        .put("base", base).put("bot_mini", bot.put("available", available)).put("billing_account_id", "a".repeat(64))

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
}
