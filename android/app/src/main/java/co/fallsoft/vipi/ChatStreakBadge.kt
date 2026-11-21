package co.fallsoft.vipi

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.text.NumberFormat
import java.util.UUID

internal val LocalStreakClock = staticCompositionLocalOf<() -> Long> { System::currentTimeMillis }

/** One clock per visible list/header. Wall-clock changes and foreground returns
 * reschedule the next UTC boundary; inactive screens perform no periodic work. */
@Composable internal fun streakCounts(vault: MessageVault?, group: Boolean, ids: List<UUID>, revision: Int): Map<UUID, Int> {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val context = LocalContext.current
    val now = LocalStreakClock.current
    var clockRevision by remember { mutableIntStateOf(0) }
    DisposableEffect(context) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) { clockRevision++ }
        }
        ContextCompat.registerReceiver(context, receiver, IntentFilter(Intent.ACTION_TIME_CHANGED), ContextCompat.RECEIVER_NOT_EXPORTED)
        onDispose { context.unregisterReceiver(receiver) }
    }
    var counts by remember(vault, group) { mutableStateOf(emptyMap<UUID, Int>()) }
    var retryAt by remember(vault) { mutableLongStateOf(0L) }
    LaunchedEffect(vault, group, ids, revision, clockRevision, lifecycle, now) {
        if (vault == null || ids.isEmpty()) return@LaunchedEffect
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            try {
                if (android.os.SystemClock.elapsedRealtime() < retryAt) return@repeatOnLifecycle
                while (true) {
                    val day = now() / ConversationStreaks.DAY_MS
                    counts = withContext(Dispatchers.IO) {
                        ConversationStreaks.counts(vault, group, ids, day)
                    }
                    val remaining = (day + 1) * ConversationStreaks.DAY_MS - now()
                    delay(remaining.coerceAtLeast(1))
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // A derived display must never interrupt a conversation. A later
                // history change, resume or visit can retry; never spin on a bad row.
                counts = emptyMap()
                retryAt = android.os.SystemClock.elapsedRealtime() + 60_000
            }
        }
    }
    return counts
}

@Composable internal fun streakNumeral(count: Int): String {
    val locale = LocalConfiguration.current.locales[0]
    return remember(count, locale) { NumberFormat.getIntegerInstance(locale).format(count) }
}

@Composable internal fun ChatStreakBadge(count: Int, group: Boolean = false, explain: Boolean = false) {
    if (count < 2) return
    val number = streakNumeral(count)
    val label = stringResource(R.string.streak_days, number)
    val rule = stringResource(if (group) R.string.streak_group_rule else R.string.streak_direct_rule)
    var showing by remember { mutableStateOf(false) }
    val action = if (explain) Modifier.clickable(role = Role.Button) { showing = true }
        .sizeIn(minWidth = 48.dp, minHeight = 48.dp) else Modifier
    Row(Modifier.testTag("chat-streak").then(action).semantics(mergeDescendants = true) { contentDescription = label },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp, Alignment.CenterHorizontally)) {
        Icon(painterResource(R.drawable.vipi_friend_streak_wave), null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
        Text(number, Modifier.clearAndSetSemantics { }, softWrap = false, maxLines = 1,
            style = MaterialTheme.typography.titleSmall.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onSurface)
    }
    if (showing) AlertDialog(onDismissRequest = { showing = false }, title = { Text(label) }, text = { Text(rule) },
        confirmButton = { TextButton(onClick = { showing = false }) { Text(stringResource(R.string.lookup_close)) } })
}
