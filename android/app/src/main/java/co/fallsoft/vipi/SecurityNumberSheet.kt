package co.fallsoft.vipi

import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
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
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun SecurityNumberSheet(chat: ChatSession, peer: java.util.UUID, dismiss: () -> Unit) {
    val context = LocalContext.current
    var number by remember(peer) { mutableStateOf<SecurityNumber?>(null) }
    var loading by remember(peer) { mutableStateOf(true) }
    var failed by remember(peer) { mutableStateOf(false) }
    var changeFailed by remember(peer) { mutableStateOf(false) }
    var recovery by remember(peer) { mutableStateOf<SignalKeys.RecoveryPreview?>(null) }
    var recoveryBusy by remember(peer) { mutableStateOf(false) }
    var recoveryError by remember(peer) { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
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
                Text(stringResource(R.string.ui_53b6cd2365c7), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = dismiss) { Text(stringResource(R.string.ui_11a6767d5674)) }
            }
            Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
            Text(chat.name(peer), style = MaterialTheme.typography.titleMedium)
            val value = number
            when {
                loading -> CircularProgressIndicator()
                failed -> {
                    Text(stringResource(R.string.ui_b47e6d6e77c8))
                    TextButton(onClick = { load() }) { Text(stringResource(R.string.try_again)) }
                }
                value == null -> Text(stringResource(R.string.ui_c754691a97ca), modifier = Modifier.testTag("identity-not-established"))
                else -> {
                    Text(stringResource(R.string.security_compare_with_friend, chat.name(peer)), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    val securityNumberDescription = stringResource(R.string.security_number_description, value.digits.toList().joinToString(", "))
                    SelectionContainer {
                        Text(value.groups.joinToString("  "),
                            style = MaterialTheme.typography.titleLarge.copy(fontFamily = FontFamily.Monospace, textDirection = TextDirection.Ltr, textAlign = TextAlign.Center),
                            modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp)).padding(20.dp)
                                .testTag("security-number").semantics { contentDescription = securityNumberDescription })
                    }
                    if (value.verified) {
                        Text(stringResource(R.string.ui_8ffeaed375d8), modifier = Modifier.testTag("identity-verified"))
                        TextButton(onClick = { change(value) }, modifier = Modifier.testTag("identity-clear")) { Text(stringResource(R.string.ui_3446735cfdee)) }
                    } else {
                        Text(stringResource(R.string.ui_8201f9bbb22b), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Button(onClick = { change(value) }, modifier = Modifier.fillMaxWidth().testTag("identity-verify")) { Text(stringResource(R.string.ui_b6ec9d55ae3b)) }
                    }
                    Text(stringResource(R.string.ui_6151d69d167a), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (changeFailed) Text(stringResource(R.string.ui_ac6b07b85d0f), style = MaterialTheme.typography.bodySmall)
                    TextButton(enabled = !recoveryBusy, onClick = {
                        recoveryBusy = true; recoveryError = null
                        scope.launch {
                            try { recovery = chat.previewPeerRecovery(peer) }
                            catch (error: CancellationException) { throw error }
                            catch (_: Exception) { recoveryError = context.getString(R.string.security_identity_check_failed) }
                            finally { recoveryBusy = false }
                        }
                    }) { Text(if (recoveryBusy) stringResource(R.string.ui_8767b4501794) else stringResource(R.string.ui_18714cc5a562)) }
                    recoveryError?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        }
    }
    recovery?.let { candidate -> AlertDialog(onDismissRequest = { if (!recoveryBusy) recovery = null },
        title = { Text(stringResource(R.string.ui_84368a0f0b2d)) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(stringResource(R.string.security_identity_changed, chat.name(peer)))
            Text(candidate.number.groups.joinToString("  "), fontFamily = FontFamily.Monospace)
            Text(stringResource(R.string.ui_84b61960effd))
            recoveryError?.let { Text(it) }
        } },
        confirmButton = { TextButton(enabled = !recoveryBusy, onClick = {
            recoveryBusy = true; recoveryError = null
            scope.launch {
                try { chat.confirmPeerRecovery(candidate); recovery = null; load() }
                catch (error: CancellationException) { throw error }
                catch (_: Exception) { recoveryError = context.getString(R.string.security_confirmation_expired) }
                finally { recoveryBusy = false }
            }
        }) { Text(if (recoveryBusy) stringResource(R.string.ui_dfe40efe921f) else stringResource(R.string.ui_8a9877b04214)) } },
        dismissButton = { TextButton(enabled = !recoveryBusy, onClick = { recovery = null }) { Text(stringResource(R.string.cancel_action)) } }) }
}
