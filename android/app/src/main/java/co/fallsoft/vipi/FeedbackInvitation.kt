package co.fallsoft.vipi

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.currentStateAsState
import com.google.android.play.core.review.ReviewManager
import com.google.android.play.core.review.ReviewManagerFactory
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

private fun Context.hostActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.takeIf { it !== this }?.hostActivity()
    else -> null
}

@Suppress("DEPRECATION")
private fun Activity.playInstalled(): Boolean = !BuildConfig.DEBUG && runCatching {
    val installer = if (Build.VERSION.SDK_INT >= 30) packageManager.getInstallSourceInfo(packageName).installingPackageName
        else packageManager.getInstallerPackageName(packageName)
    installer == "com.android.vending"
}.getOrDefault(false)

@Composable internal fun FeedbackInvitation(chat: ChatSession, session: String) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val resumed = lifecycle.currentStateAsState().value == Lifecycle.State.RESUMED
    val activity = LocalContext.current.hostActivity()
    val scope = rememberCoroutineScope()
    var survey by remember(chat) { mutableStateOf(false) }
    LaunchedEffect(chat, session, resumed) {
        if (!resumed) { survey = false; return@LaunchedEffect }
        val returned = chat.takeFeedbackReturn()
        val ledger = chat.feedback ?: return@LaunchedEffect
        try {
            chat.retryFundingChoice()
            if (!returned) return@LaunchedEffect
            ledger.includeEarlierMessages()
            fun eligible(kind: FeedbackPrompt) = ledger.eligible(kind, session, System.currentTimeMillis())
            if (eligible(FeedbackPrompt.SURVEY) && chat.fundingSurveyAvailable(session)) {
                survey = ledger.claim(FeedbackPrompt.SURVEY, session, System.currentTimeMillis())
            }
            if (!survey && activity != null && activity.playInstalled() && chat.eventDevice() != null &&
                lifecycle.currentState == Lifecycle.State.RESUMED &&
                ledger.claim(FeedbackPrompt.REVIEW, session, System.currentTimeMillis())) {
                requestNativeReview(activity, ReviewManagerFactory.create(activity)) {
                    chat.eventDevice() != null && lifecycle.currentState == Lifecycle.State.RESUMED
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { /* Optional invitations must leave the inbox usable. */ }
    }
    if (survey && resumed) FundingQuestion { choice ->
        if (survey) {
            chat.feedback?.queue(choice)
            survey = false
            scope.launch { chat.retryFundingChoice() }
        }
    }
}

internal suspend fun requestNativeReview(activity: Activity, manager: ReviewManager, mayPresent: () -> Boolean) {
    val info = manager.requestReviewFlow().await()
    if (!activity.isFinishing && !activity.isDestroyed && mayPresent()) manager.launchReviewFlow(activity, info).await()
}

@Composable internal fun FundingQuestion(answer: (FundingChoice) -> Unit) {
    Surface(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surfaceContainer,
        contentColor = MaterialTheme.colorScheme.onSurface) {
        // Let large type scroll independently while the inbox and its navigation stay reachable.
        Column(Modifier.heightIn(max = 280.dp).verticalScroll(rememberScrollState()).padding(16.dp)) {
            Text(stringResource(R.string.funding_question), style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.funding_context), style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                for ((choice, title) in listOf(FundingChoice.YES to R.string.funding_yes,
                    FundingChoice.MAYBE to R.string.funding_maybe, FundingChoice.NO to R.string.funding_no)) {
                    OutlinedButton(onClick = { answer(choice) }) { Text(stringResource(title)) }
                }
                TextButton(onClick = { answer(FundingChoice.SKIP) }) { Text(stringResource(R.string.funding_skip)) }
            }
        }
    }
}
