package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

internal data class MessageChoice(val id: String, val original: String)

/** Selection only: the existing review dialog owns consent and submission. */
@Composable
internal fun MessageReportChooser(
    messages: List<MessageChoice>,
    select: (String) -> Unit,
    dismiss: () -> Unit,
) = MessageChooser(messages, R.string.report_message, "report", select, dismiss)

/**
 * Touch-accessible original copying is independent of report eligibility. Neither
 * translated/reading faces nor the conversation's tap-to-play surface participate in this dialog.
 */
@Composable
internal fun MessageOriginalChooser(messages: List<MessageChoice>, dismiss: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    MessageChooser(
        messages,
        R.string.full_translation_copy_original,
        "copy",
        { id ->
            messages
                .singleOrNull { it.id == id }
                ?.let { selected ->
                    context
                        .getSystemService(android.content.ClipboardManager::class.java)
                        .setPrimaryClip(
                            android.content.ClipData.newPlainText("", selected.original)
                        )
                }
            dismiss()
        },
        dismiss,
    )
}

@Composable
private fun MessageChooser(
    messages: List<MessageChoice>,
    title: Int,
    tag: String,
    select: (String) -> Unit,
    dismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = dismiss,
        title = { Text(stringResource(title)) },
        text = {
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 360.dp).testTag("$tag-choices")) {
                items(messages, key = { it.id }) { message ->
                    TextButton(
                        onClick = { select(message.id) },
                        modifier =
                            Modifier.fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .testTag("$tag-choice-${message.id}"),
                    ) {
                        Text(
                            message.original,
                            textAlign = TextAlign.Start,
                            maxLines = 4,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = dismiss) { Text(stringResource(R.string.cancel_action)) }
        },
    )
}
