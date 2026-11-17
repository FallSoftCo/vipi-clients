package co.fallsoft.vipi

import android.app.Activity
import android.content.ContextWrapper
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.NumberFormat
import java.time.ZoneId
import java.time.Instant
import java.time.Duration
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Currency
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

@Composable internal fun SubscriptionScreen(model: VipiModel, plan: SubscriptionPlan = SubscriptionPlan.BASE) {
    val subscriptions = model.subscriptions
    val context = LocalContext.current
    val activity = generateSequence(context) { (it as? ContextWrapper)?.baseContext?.takeIf { next -> next !== it } }.filterIsInstance<Activity>().firstOrNull()
    val uri = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    var linkError by remember { mutableStateOf<String?>(null) }
    var botAllowance by remember { mutableStateOf<BotAllowance?>(null) }
    LaunchedEffect(subscriptions, plan) { subscriptions?.refresh() }
    LaunchedEffect(plan, model.authentication.userID) {
        if (plan == SubscriptionPlan.BOT_MINI) {
            val user = model.authentication.userID
            if (user != null) try { botAllowance = BotAllowance.parse(ServiceClient(model.authentication, user).request("GET", "/v1/bot/allowance")) }
            catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
            catch (_: Exception) { botAllowance = null }
        }
    }
    fun open(url: String) { try { uri.openUri(url) } catch (_: Exception) { linkError = context.getString(R.string.plan_link_error) } }
    Text(if (plan == SubscriptionPlan.BASE) stringResource(R.string.ui_42f4f8b469bb) else stringResource(R.string.ui_f80c9ded3433), fontFamily = FontFamily.Serif, fontSize = 30.sp, lineHeight = 36.sp)
    Text(if (plan == SubscriptionPlan.BASE) stringResource(R.string.base_plan_description)
        else stringResource(R.string.bot_plan_description), lineHeight = 23.sp)
    if (plan == SubscriptionPlan.BOT_MINI) Text(stringResource(R.string.ui_c518ff733bfe), style = MaterialTheme.typography.bodyMedium)
    if (plan == SubscriptionPlan.BOT_MINI) {
        val amount = botAllowance?.takeIf { it.serviceReady }?.monthly?.takeIf { it > 0 }
        Text(if (amount != null) androidx.compose.ui.res.pluralStringResource(R.plurals.bot_monthly_allowance, amount, NumberFormat.getIntegerInstance().format(amount))
            else stringResource(R.string.bot_allowance_unavailable), style = MaterialTheme.typography.bodyMedium)
    }
    if (subscriptions == null) {
        Text(stringResource(R.string.ui_28e67a870e46))
        Button(onClick = { model.navigate(Screen.ACCOUNT) }) { Text(stringResource(R.string.nav_sign_in)) }
        return
    }
    val snapshot = subscriptions.access
    val access = if (plan == SubscriptionPlan.BASE) snapshot?.base else snapshot?.bot
    val offer = subscriptions.offers[plan]
    var now by remember(subscriptions, plan, snapshot) { mutableStateOf(snapshot?.serverNow() ?: Instant.now()) }
    var expiryRefreshPending by remember(subscriptions, plan, access?.expiresAt) {
        mutableStateOf(access?.active == true && access.expiresAt?.let { !it.isAfter(snapshot?.serverNow() ?: Instant.now()) } == true)
    }
    LaunchedEffect(subscriptions, plan, access?.expiresAt) {
        val expiry = access?.expiresAt ?: return@LaunchedEffect
        val wait = Duration.between(snapshot?.serverNow() ?: Instant.now(), expiry).toMillis()
        if (wait > 0) delay(wait)
        expiryRefreshPending = true
        now = snapshot?.serverNow() ?: Instant.now()
        try { subscriptions.refresh() } finally { expiryRefreshPending = false }
    }
    val verificationUnavailable = plan == SubscriptionPlan.BOT_MINI && access?.verificationUnavailable == true
    val clockUnavailable = snapshot != null && snapshot.serverTime == null
    val accessUnknown = expiryRefreshPending || subscriptions.accessCheckState != AccessCheckState.LOADED || verificationUnavailable || clockUnavailable
    if (access?.usable(now) == true && !accessUnknown) {
        PlanAccessSummary(plan, access, now)
        if (plan == SubscriptionPlan.BOT_MINI && snapshot?.base?.usable(now) != true) Text(stringResource(R.string.bot_requires_vipi_access))
        if (plan == SubscriptionPlan.BASE) Button(onClick = { model.navigate(Screen.HOME) }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ui_a2a2eed05c81)) }
        else if (snapshot?.active(SubscriptionPlan.BOT_MINI) == true) Button(onClick = { model.openBot() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ui_c6046d416aaf)) }
    } else if (accessUnknown) {
        Text(if (verificationUnavailable) stringResource(R.string.bot_verification_unavailable) else if (clockUnavailable || subscriptions.accessCheckState == AccessCheckState.ERROR) stringResource(R.string.plan_clock_unavailable) else stringResource(R.string.ui_ee7fdea20d0b), style = MaterialTheme.typography.bodyMedium)
    } else if (offer != null) {
        Text(if (offer.oneMonthTrial) stringResource(R.string.trial_then_annual, offer.annualPrice) else stringResource(R.string.annual_price, offer.annualPrice), fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
        Text(if (offer.oneMonthTrial) stringResource(R.string.play_trial_renewal_description)
            else if (plan == SubscriptionPlan.BASE) stringResource(R.string.annual_renewal_description)
            else stringResource(R.string.no_trial_renewal_description), style = MaterialTheme.typography.bodyMedium)
        if (plan == SubscriptionPlan.BOT_MINI) {
            val base = subscriptions.offers[SubscriptionPlan.BASE]
            if (base != null) {
                val total = if (base.currency == offer.currency) runCatching {
                    NumberFormat.getCurrencyInstance().apply { currency = Currency.getInstance(offer.currency) }
                        .format(java.math.BigDecimal.valueOf(base.annualMicros + offer.annualMicros, 6))
                }.getOrNull() else null
                Text(if (total != null) stringResource(R.string.both_plans_total, total)
                    else stringResource(R.string.both_plans_separate, base.annualPrice, offer.annualPrice))
            }
            if (snapshot?.base?.usable(now) != true) {
                Text(stringResource(R.string.ui_6802cad312c0))
                TextButton(onClick = { model.navigate(Screen.PLANS) }) { Text(stringResource(R.string.ui_2090b85775b4)) }
            }
        }
        Button(onClick = { activity?.let { subscriptions.buy(it, plan) } }, modifier = Modifier.fillMaxWidth(),
            enabled = activity != null && snapshot?.purchasesReady == true && !subscriptions.busy && !subscriptions.purchasing &&
                (plan == SubscriptionPlan.BASE || (snapshot?.base?.usable(now) == true && subscriptions.offers[SubscriptionPlan.BASE] != null && botAllowance?.serviceReady == true && (botAllowance?.monthly ?: 0) > 0))) {
            Text(if (subscriptions.purchasing) stringResource(R.string.ui_0c86126aea39) else if (offer.oneMonthTrial) stringResource(R.string.ui_33a6e5e20062) else stringResource(R.string.subscribe_annual, offer.annualPrice))
        }
    }
    if (subscriptions.busy) CircularProgressIndicator(Modifier.size(24.dp))
    if (snapshot != null && !snapshot.purchasesReady) Text(stringResource(R.string.ui_825bf52ce678), style = MaterialTheme.typography.bodySmall)
    subscriptions.notice?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    TextButton(onClick = { scope.launch { subscriptions.refresh() } }, enabled = !subscriptions.busy && !subscriptions.purchasing) { Text(stringResource(R.string.ui_3ceeccf6b3ff)) }
    TextButton(onClick = { open("https://play.google.com/store/account/subscriptions") }) { Text(stringResource(R.string.ui_02d207068808)) }
    Text(stringResource(R.string.ui_57225bd8b984), style = MaterialTheme.typography.bodySmall)
    Row {
        TextButton(onClick = { open("https://api.mambovipi.app/terms") }) { Text(stringResource(R.string.nav_terms)) }
        TextButton(onClick = { open("https://api.mambovipi.app/privacy") }) { Text(stringResource(R.string.nav_privacy)) }
    }
    linkError?.let { Text(it) }
}

/** Shared by the normal plan screen and isolated native UI qualification. */
@Composable internal fun PlanAccessSummary(plan: SubscriptionPlan, access: PlanAccess,
    now: java.time.Instant = java.time.Instant.now()) {
    if (!access.usable(now)) return
    if (plan == SubscriptionPlan.BASE && access.accessSource == "cardless_trial" && access.cardlessTrial?.active == true) {
        val end = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT).withZone(ZoneId.systemDefault()).format(access.cardlessTrial.endsAt)
        Text(stringResource(R.string.cardless_ends, end), fontWeight = FontWeight.SemiBold)
        Text(stringResource(R.string.cardless_no_autocharge), style = MaterialTheme.typography.bodyMedium)
        return
    }
    Text(if (access.reviewAccess) stringResource(R.string.review_access_description)
        else stringResource(R.string.plan_active, plan.title), fontWeight = FontWeight.SemiBold)
    val trial = access.trialEndsAt?.takeIf { it.isAfter(now) }
    val until = trial ?: access.expiresAt
    until?.let { Text(stringResource(if (trial != null) R.string.trial_end_date else R.string.access_end_date, DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withZone(ZoneId.systemDefault()).format(it))) }
}
