package co.fallsoft.vipi

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** Only in-memory server-shaped fixtures and the production plan summary.
 * Does not construct authentication, Subscriptions, BillingClient or a transport;
 * does not write any grant/account/preferences/history or perform a network call. */
class ReviewPlanAccessDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val now = Instant.parse("2026-11-11T00:00:00Z")
    private val reviewText = "Review access is active. No subscription is required for this account."
    private fun ordinary(expiry: String? = "2026-12-11T00:00:00Z", active: Boolean = true) = JSONObject()
        .put("active", active).put("expires_at", expiry ?: JSONObject.NULL).put("trial_ends_at", JSONObject.NULL)
    private fun review(active: Boolean = true) = ordinary(null, active)
        .put("access_source", "review_complimentary").put("review_access", true)
    private fun snapshot(base: JSONObject, bot: JSONObject, available: Boolean) = SubscriptionAccess.parse(JSONObject()
        .put("base", base).put("bot_mini", bot.put("available", available))
        .put("billing_account_id", "b".repeat(64)).put("server_time", Instant.now().toString()).put("purchases_ready", JSONObject().put("google", false)))

    @Test fun normalExpiryAndTrialPresentationPreservesPaidRules() {
        val value = mutableStateOf(PlanAccess.parse(ordinary()))
        compose.setContent { Column { PlanAccessSummary(SubscriptionPlan.BASE, value.value, now) } }
        compose.onNodeWithText("Vipi is active").assertIsDisplayed()
        compose.onNodeWithText("Current access ends", substring = true).assertIsDisplayed()
        compose.onNodeWithText(reviewText).assertDoesNotExist()
        compose.runOnIdle { value.value = PlanAccess.parse(ordinary().put("trial_ends_at", "2026-11-20T00:00:00Z")) }
        compose.onNodeWithText("Trial ends", substring = true).assertIsDisplayed()
        compose.runOnIdle { value.value = PlanAccess.parse(ordinary(now.toString())) }
        compose.onNodeWithText("Vipi is active").assertDoesNotExist()
        compose.onNodeWithText("Trial ends", substring = true).assertDoesNotExist()
        compose.onNodeWithText(reviewText).assertDoesNotExist()
    }

    @Test fun explicitlyMarkedReviewPresentationDoesNotInventRenewalOrTrial() {
        val value = mutableStateOf(PlanAccess.parse(review()))
        compose.setContent { Column { PlanAccessSummary(SubscriptionPlan.BOT_MINI, value.value, now) } }
        compose.onNodeWithText(reviewText).assertIsDisplayed()
        compose.onNodeWithText("Current access ends", substring = true).assertDoesNotExist()
        compose.onNodeWithText("Trial ends", substring = true).assertDoesNotExist()
        compose.runOnIdle { value.value = PlanAccess.parse(review(false)) }
        compose.onNodeWithText(reviewText).assertDoesNotExist()
    }

    @Test fun markersAndBothPlanGatesStayAccountBoundAndFailClosed() {
        assertFalse(PlanAccess.parse(ordinary(null)).usable(now))
        assertFalse(PlanAccess.parse(ordinary(null).put("review_access", true)).usable(now))
        assertFalse(PlanAccess.parse(ordinary(null).put("access_source", "review_complimentary")).usable(now))
        assertFalse(PlanAccess.parse(review().put("review_access", "true")).usable(now))
        assertFalse(PlanAccess.parse(review().put("access_source", "other")).usable(now))
        assertTrue(runCatching { PlanAccess.parse(review().put("expires_at", "2026-12-11T00:00:00Z")) }.isFailure)
        val both = snapshot(review(), review(), true)
        assertTrue(both.active(SubscriptionPlan.BASE)); assertTrue(both.active(SubscriptionPlan.BOT_MINI))
        assertFalse(both.purchasesReady)
        val baseOnly = snapshot(review(), ordinary(null, false), true)
        assertTrue(baseOnly.active(SubscriptionPlan.BASE)); assertFalse(baseOnly.active(SubscriptionPlan.BOT_MINI))
        assertFalse(snapshot(review(false), review(), true).active(SubscriptionPlan.BOT_MINI))
        assertFalse(snapshot(review(), review(), false).active(SubscriptionPlan.BOT_MINI))
        assertFalse(snapshot(ordinary("2020-01-01T00:00:00Z"), review(), true).active(SubscriptionPlan.BASE))
        assertFalse(snapshot(ordinary("2020-01-01T00:00:00Z"), review(), true).active(SubscriptionPlan.BOT_MINI))
    }
}
