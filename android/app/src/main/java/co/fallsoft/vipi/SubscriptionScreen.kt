package co.fallsoft.vipi

import android.app.Activity
import android.content.ContextWrapper
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.NumberFormat
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Currency
import kotlinx.coroutines.launch

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
    fun open(url: String) { try { uri.openUri(url) } catch (_: Exception) { linkError = "This link couldn’t open. Please try again." } }
    Text(if (plan == SubscriptionPlan.BASE) "A new language,\nin your everyday life." else "More conversation\nwith vBot.", fontFamily = FontFamily.Serif, fontSize = 30.sp, lineHeight = 36.sp)
    Text(if (plan == SubscriptionPlan.BASE) "Private chats, local immersion, and offline speech. Bot mini is a separate, optional plan."
        else "Bot mini adds vBot to your Vipi plan. It is a separate subscription, with its own renewal date.", lineHeight = 23.sp)
    if (plan == SubscriptionPlan.BOT_MINI) Text("vBot is powered by DeepSeek. Messages you send to vBot go to Vipi and DeepSeek to generate replies. Your chats with friends are never included automatically.", style = MaterialTheme.typography.bodyMedium)
    if (plan == SubscriptionPlan.BOT_MINI) {
        val amount = botAllowance?.takeIf { it.serviceReady }?.monthly?.takeIf { it > 0 }
        Text(if (amount != null) "$amount replies per calendar month. Unused replies don’t roll over; no automatic overage charges."
            else "Bot mini isn’t available to start yet. Its monthly allowance must be confirmed first.", style = MaterialTheme.typography.bodyMedium)
    }
    if (subscriptions == null) {
        Text("Sign in to see the plans available for your account.")
        Button(onClick = { model.navigate(Screen.ACCOUNT) }) { Text("Sign in") }
        return
    }
    val snapshot = subscriptions.access
    val access = if (plan == SubscriptionPlan.BASE) snapshot?.base else snapshot?.bot
    val offer = subscriptions.offers[plan]
    if (access?.usable() == true) {
        Text("${plan.title} is active", fontWeight = FontWeight.SemiBold)
        val trial = access.trialEndsAt?.takeIf { it.isAfter(java.time.Instant.now()) }
        val until = trial ?: access.expiresAt
        until?.let { Text("${if (trial != null) "Trial ends" else "Current access ends"} ${DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withZone(ZoneId.systemDefault()).format(it)}.") }
        if (plan == SubscriptionPlan.BOT_MINI && snapshot?.base?.usable() != true) Text("Bot mini needs an active Vipi plan. Restore Vipi or manage Bot mini in Google Play to prevent another renewal.")
        if (plan == SubscriptionPlan.BASE) Button(onClick = { model.navigate(Screen.HOME) }, modifier = Modifier.fillMaxWidth()) { Text("Continue to chats") }
        else if (snapshot?.active(SubscriptionPlan.BOT_MINI) == true) Button(onClick = { model.openBot() }, modifier = Modifier.fillMaxWidth()) { Text("Continue to vBot") }
    } else if (offer != null) {
        Text(if (offer.oneMonthTrial) "One month free, then ${offer.annualPrice} per year" else "${offer.annualPrice} per year", fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
        Text(if (offer.oneMonthTrial) "Google Play confirms your eligibility and first payment date at checkout. The annual subscription renews automatically unless you cancel."
            else "A free trial isn’t available for this offer. The annual subscription renews automatically unless you cancel.", style = MaterialTheme.typography.bodyMedium)
        if (plan == SubscriptionPlan.BOT_MINI) {
            val base = subscriptions.offers[SubscriptionPlan.BASE]
            if (base != null) {
                val total = if (base.currency == offer.currency) runCatching {
                    NumberFormat.getCurrencyInstance().apply { currency = Currency.getInstance(offer.currency) }
                        .format(java.math.BigDecimal.valueOf(base.annualMicros + offer.annualMicros, 6))
                }.getOrNull() else null
                Text(if (total != null) "Both plans: $total per year after trials, billed separately."
                    else "Vipi: ${base.annualPrice} per year. Bot mini: ${offer.annualPrice} additional per year. Billed separately.")
            }
            if (snapshot?.base?.usable() != true) {
                Text("Start or restore Vipi before adding Bot mini.")
                TextButton(onClick = { model.navigate(Screen.PLANS) }) { Text("View Vipi plan") }
            }
        }
        Button(onClick = { activity?.let { subscriptions.buy(it, plan) } }, modifier = Modifier.fillMaxWidth(),
            enabled = activity != null && snapshot?.purchasesReady == true && !subscriptions.busy && !subscriptions.purchasing &&
                (plan == SubscriptionPlan.BASE || (snapshot?.base?.usable() == true && subscriptions.offers[SubscriptionPlan.BASE] != null && botAllowance?.serviceReady == true && (botAllowance?.monthly ?: 0) > 0))) {
            Text(if (subscriptions.purchasing) "Waiting for Google Play…" else if (offer.oneMonthTrial) "Start one-month free trial" else "Subscribe for ${offer.annualPrice} per year")
        }
    }
    if (subscriptions.busy) CircularProgressIndicator(Modifier.size(24.dp))
    if (snapshot != null && !snapshot.purchasesReady) Text("Google Play purchases aren’t available yet. Existing plans can still be restored.", style = MaterialTheme.typography.bodySmall)
    subscriptions.notice?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    TextButton(onClick = { scope.launch { subscriptions.refresh() } }, enabled = !subscriptions.busy && !subscriptions.purchasing) { Text("Restore purchases or refresh plans") }
    TextButton(onClick = { open("https://play.google.com/store/account/subscriptions") }) { Text("Manage subscriptions in Google Play") }
    Text("You can always read saved conversations and delete your account, even without an active plan.", style = MaterialTheme.typography.bodySmall)
    Row {
        TextButton(onClick = { open("https://api.mambovipi.app/terms") }) { Text("Terms") }
        TextButton(onClick = { open("https://api.mambovipi.app/privacy") }) { Text("Privacy") }
    }
    linkError?.let { Text(it) }
}
