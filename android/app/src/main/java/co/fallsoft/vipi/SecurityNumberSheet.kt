package co.fallsoft.vipi

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun SecurityNumberSheet(chat: ChatSession, peer: java.util.UUID, dismiss: () -> Unit) {
    var number by remember(peer) { mutableStateOf<SecurityNumber?>(null) }
    var loading by remember(peer) { mutableStateOf(true) }
    var failed by remember(peer) { mutableStateOf(false) }
    var changeFailed by remember(peer) { mutableStateOf(false) }
    fun load() {
        try { number = chat.securityNumber(peer); failed = false }
        catch (_: Exception) { number = null; failed = true }
        loading = false
    }
    fun change(value: SecurityNumber) {
        try { chat.setIdentityVerified(!value.verified, peer, value); changeFailed = false; load() }
        catch (_: Exception) { changeFailed = true; load() }
    }
    LaunchedEffect(peer) { load() }
    val contentDensity = LocalDensity.current
    val lightBars = MaterialTheme.colorScheme.background.luminance() > 0.5f
    ModalBottomSheet(onDismissRequest = dismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        properties = ModalBottomSheetProperties(isAppearanceLightStatusBars = lightBars, isAppearanceLightNavigationBars = lightBars)) {
        // The sheet owns another Android window. Retain the parent text scale
        // and update its system bars when the app's appearance changes.
        CompositionLocalProvider(LocalDensity provides contentDensity) {
        val sheetView = LocalView.current
        SideEffect {
            // Material3 1.4.0 applies system-bar properties only when its dialog
            // is constructed. Keep the existing window correct on theme changes.
            (sheetView.parent as? DialogWindowProvider)?.window?.let { window ->
                WindowCompat.getInsetsController(window, window.decorView).apply {
                    isAppearanceLightStatusBars = lightBars
                    isAppearanceLightNavigationBars = lightBars
                }
            }
        }
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Verify encryption", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = dismiss) { Text("Done") }
            }
            Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
            Text(chat.name(peer), style = MaterialTheme.typography.titleMedium)
            val value = number
            when {
                loading -> CircularProgressIndicator()
                failed -> {
                    Text("Encryption details couldn’t be opened. Your verification hasn’t changed.")
                    TextButton(onClick = { load() }) { Text("Try again") }
                }
                value == null -> Text("Exchange a message first to create this conversation’s security number.", modifier = Modifier.testTag("identity-not-established"))
                else -> {
                    Text("Compare all 12 groups with ${chat.name(peer)} in person or over a trusted call to confirm your encryption keys match.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SelectionContainer {
                        Text(value.groups.joinToString("  "),
                            style = MaterialTheme.typography.titleLarge.copy(fontFamily = FontFamily.Monospace, textDirection = TextDirection.Ltr, textAlign = TextAlign.Center),
                            modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp)).padding(20.dp)
                                .testTag("security-number").semantics { contentDescription = "Security number, " + value.digits.toList().joinToString(", ") })
                    }
                    if (value.verified) {
                        Text("You verified these keys", modifier = Modifier.testTag("identity-verified"))
                        TextButton(onClick = { change(value) }, modifier = Modifier.testTag("identity-clear")) { Text("Clear verification") }
                    } else {
                        Text("Not yet compared", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Button(onClick = { change(value) }, modifier = Modifier.fillMaxWidth().testTag("identity-verify")) { Text("I compared all 12 groups") }
                    }
                    Text("If any group differs, don’t mark it as verified. A new phone or reinstalled app can change these numbers.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (changeFailed) Text("The keys may have changed, or your choice couldn’t be saved. Compare the current numbers again.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        }
    }
}
