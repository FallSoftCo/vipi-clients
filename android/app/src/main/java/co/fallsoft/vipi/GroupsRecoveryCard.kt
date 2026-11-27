package co.fallsoft.vipi

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import java.util.UUID
import kotlinx.coroutines.launch

/**
 * Optional recovery inside Group info, never launch navigation. A cancellation is server-confirmed
 * before the current-people sheet can offer local closure.
 */
@Composable
internal fun GroupRecoveryCard(session: GroupsSession, group: UUID) {
    val scope = rememberCoroutineScope()
    val available = session.recoveryAvailable(group)
    val cancelled = session.recoveryCancelled(group)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            if (cancelled)
                "Vipi confirmed this change was cancelled. Review the current people before closing it."
            else
                "If the saved change was already applied, checking will recover its original result. Otherwise, Vipi will cancel that exact change.",
            style = MaterialTheme.typography.bodyLarge,
        )
        TextButton(
            enabled = available && !session.busy,
            modifier = Modifier.testTag("group-check-saved-change"),
            onClick = { scope.launch { session.checkSavedChange(group) } },
        ) {
            Text(if (cancelled) "Review current people" else "Check or cancel saved change")
        }
        if (!available)
            Text(
                "This earlier change was saved without its original device details. You can retry it exactly; it cannot be cancelled automatically.",
                style = MaterialTheme.typography.bodyMedium,
            )
    }
    session.recoveryReview
        ?.takeIf { it.current.id == group }
        ?.let { review ->
            AlertDialog(
                onDismissRequest = session::dismissRecoveryReview,
                modifier = Modifier.testTag("group-cancelled-review"),
                title = { Text("Close the cancelled change?") },
                text = {
                    Column(
                        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text(
                            "The original change was not applied. Your saved messages remain. Review the current people, then choose a new change afterward.",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                        Text(review.current.title, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Current people (${review.current.members.size})",
                            style = MaterialTheme.typography.titleSmall,
                        )
                        review.current.members.forEach { person ->
                            Text(
                                "${person.name} · ${person.role.wire}",
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        }
                        if (review.current.invitations.isNotEmpty())
                            Text(
                                "${review.current.invitations.size} invitations are still waiting for an answer.",
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        Text(
                            "Reviewing this list does not approve new encryption identities or membership.",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        session.notice?.let {
                            Text(
                                it,
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        }
                    }
                },
                confirmButton = {
                    TextButton(
                        enabled = !session.busy,
                        modifier = Modifier.testTag("group-close-cancelled-change"),
                        onClick = { scope.launch { session.confirmCancelledChange() } },
                    ) {
                        Text("Close saved change")
                    }
                },
                dismissButton = {
                    TextButton(enabled = !session.busy, onClick = session::dismissRecoveryReview) {
                        Text("Not now")
                    }
                },
            )
        }
}
