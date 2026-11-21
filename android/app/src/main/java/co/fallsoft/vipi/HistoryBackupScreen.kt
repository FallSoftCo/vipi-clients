package co.fallsoft.vipi

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.Alignment
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import java.io.File
import android.content.Context
import java.nio.file.Files
import java.io.FileOutputStream
import java.util.UUID
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel

/** Private encrypted transfer copies belong to the stable Vipi account UUID.
 * Legacy unscoped copies have no trustworthy owner tag and are preserved. */
internal object HistoryTransferFiles {
    private fun directory(context: Context, account: UUID): File {
        val root = File(context.noBackupFilesDir.canonicalFile, "history-transfer")
        val owned = File(root, account.toString())
        check(root.canonicalFile == root && owned.canonicalFile == owned) { "Invalid private transfer directory" }
        return owned
    }
    fun temporary(context: Context, account: UUID): File {
        val directory = directory(context, account)
        check(directory.isDirectory || directory.mkdirs()) { "Private transfer directory unavailable" }
        return File(directory, "${UUID.randomUUID()}.vipihistory")
    }
    fun erase(context: Context, account: UUID) {
        fun remove(file: File) {
            // Never follow a link into another account or a user-selected file.
            if (!Files.isSymbolicLink(file.toPath()) && file.isDirectory) {
                val children = checkNotNull(file.listFiles()) { "Private transfer cleanup incomplete" }
                children.forEach(::remove)
            }
            check(!file.exists() && !Files.isSymbolicLink(file.toPath()) || file.delete()) { "Private transfer cleanup incomplete" }
        }
        remove(directory(context, account))
    }
}

/** In-memory only across rotation; secrets never enter saved-state bundles. */
internal class HistoryBackupModel : ViewModel() {
    var password by mutableStateOf("")
    var confirmation by mutableStateOf("")
    var restoring by mutableStateOf(false)
    var busy by mutableStateOf(false)
    var message by mutableStateOf<String?>(null)
    var summary by mutableStateOf<HistoryBackupCodec.Inspection?>(null)
    var staged by mutableStateOf<File?>(null)
    var exported by mutableStateOf<File?>(null)
    var job: Job? = null
    var invalidPassword by mutableStateOf(false)
    var mismatchedConfirmation by mutableStateOf(false)
    suspend fun prepareExport(file: File, write: suspend (File) -> Unit) {
        var retained = false
        try {
            write(file)
            currentCoroutineContext().ensureActive()
            exported = file; retained = true
        } finally {
            // IO can finish after clear() cancels the job. Its owned copy must
            // still be removed before the cancelled export completes.
            if (!retained) file.delete()
        }
    }
    fun clear() {
        job?.cancel(); job = null; staged?.delete(); staged = null; exported?.delete(); exported = null
        password = ""; confirmation = ""; summary = null; message = null; busy = false
        invalidPassword = false; mismatchedConfirmation = false
    }
    override fun onCleared() { clear() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun HistoryBackupScreen(chat: ChatSession, back: () -> Unit) {
    val context = LocalContext.current
    val account = chat.profile?.id ?: run { Text(stringResource(R.string.backup_open_failed)); return }
    val transfer: HistoryBackupModel = viewModel(key = "history-transfer-$account")
    val scope = transfer.viewModelScope
    var password by transfer::password
    var confirmation by transfer::confirmation
    var restoring by transfer::restoring
    var busy by transfer::busy
    var message by transfer::message
    var summary by transfer::summary
    var staged by transfer::staged
    var exported by transfer::exported
    var job by transfer::job
    var invalidPassword by transfer::invalidPassword
    var mismatchedConfirmation by transfer::mismatchedConfirmation
    var validationAttempt by remember { mutableIntStateOf(0) }
    val keyboardBottom = WindowInsets.ime.getBottom(LocalDensity.current)
    val passwordIntoView = remember { BringIntoViewRequester() }
    val confirmationIntoView = remember { BringIntoViewRequester() }
    val passwordFocus = remember { FocusRequester() }
    val confirmationFocus = remember { FocusRequester() }
    val normalizedPassword = remember(password) { java.text.Normalizer.normalize(password, java.text.Normalizer.Form.NFC) }
    val passwordFeedback = when {
        !invalidPassword -> R.string.ui_04c8049b72ff
        normalizedPassword.codePointCount(0, normalizedPassword.length) < 12 -> R.string.backup_password_too_short
        normalizedPassword.toByteArray(Charsets.UTF_8).size > 1024 -> R.string.backup_password_too_long
        else -> R.string.ui_04c8049b72ff
    }
    fun validate(requireConfirmation: Boolean): Boolean {
        invalidPassword = !HistoryBackupCodec.validPassword(password)
        mismatchedConfirmation = !invalidPassword && requireConfirmation && password != confirmation
        val field = when {
            invalidPassword -> passwordFocus
            mismatchedConfirmation -> confirmationFocus
            else -> return true
        }
        field.requestFocus()
        validationAttempt++
        return false
    }
    LaunchedEffect(validationAttempt, keyboardBottom, invalidPassword, mismatchedConfirmation) {
        val field = when {
            invalidPassword -> passwordIntoView
            mismatchedConfirmation -> confirmationIntoView
            else -> return@LaunchedEffect
        }
        // Repeat for the actual changing IME viewport: a request fulfilled
        // before the keyboard opens must not leave its explanation underneath.
        withFrameNanos { }
        field.bringIntoView()
    }
    fun temporary() = HistoryTransferFiles.temporary(context, account)
    fun clearImport() { staged?.delete(); staged = null; summary = null }
    fun failure(error: Exception) {
        message = if (error is HistoryBackupCodec.DifferentAccount) context.getString(R.string.backup_wrong_account)
        else context.getString(R.string.backup_open_failed)
    }
    DisposableEffect(context, account, transfer) { onDispose {
        var owner = context
        while (owner is android.content.ContextWrapper && owner !is android.app.Activity) owner = owner.baseContext
        if ((owner as? android.app.Activity)?.isChangingConfigurations != true) transfer.clear()
    } }
    BackHandler { job?.cancel(); back() }
    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        val file = exported
        if (uri == null || file == null) { file?.delete(); exported = null; busy = false }
        else job = scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    requireNotNull(context.contentResolver.openOutputStream(uri, "wt")).use { output ->
                        file.inputStream().use { input ->
                            val buffer = ByteArray(65536)
                            while (true) { ensureActive(); val count = input.read(buffer); if (count == -1) break; output.write(buffer, 0, count) }
                        }
                        output.flush()
                    }
                }
                message = context.getString(R.string.backup_saved)
            } catch (error: CancellationException) { throw error }
            catch (error: Exception) { message = context.getString(R.string.backup_save_failed) }
            finally { file.delete(); exported = null; password = ""; confirmation = ""; busy = false }
        }
    }
    val open = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) busy = false
        else job = scope.launch {
            var file: File? = null
            try {
                clearImport(); file = temporary(); val owned = file
                withContext(Dispatchers.IO) {
                    requireNotNull(context.contentResolver.openInputStream(uri)).use { input ->
                        FileOutputStream(owned).use { output ->
                            val buffer = ByteArray(65536); var total = 0L
                            while (true) {
                                ensureActive(); val count = input.read(buffer); if (count == -1) break
                                total += count; require(total <= HistoryBackupCodec.MAX_FILE_BYTES); output.write(buffer, 0, count)
                            }
                            output.fd.sync()
                        }
                    }
                    check(owned.setWritable(false, true))
                }
                summary = chat.inspectHistory(owned, password); staged = owned; file = null
            } catch (error: CancellationException) { throw error }
            catch (error: Exception) { failure(error) }
            finally { file?.delete(); busy = false }
        }
    }
    Scaffold(topBar = { TopAppBar(title = { Text(stringResource(R.string.ui_24f13e3dc8e4)) }, navigationIcon = {
        IconButton(onClick = { job?.cancel(); back() }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) }
    }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(stringResource(R.string.backup_intent), style = MaterialTheme.typography.bodyLarge)
            listOf(false to stringResource(R.string.ui_6a6965bcf571), true to stringResource(R.string.ui_beb6c51b9bf6)).forEach { (restore, label) ->
                Row(Modifier.fillMaxWidth().selectable(selected = restoring == restore, enabled = !busy, role = Role.RadioButton, onClick = {
                    if (restoring != restore) { clearImport(); confirmation = ""; message = null; invalidPassword = false; mismatchedConfirmation = false; restoring = restore }
                }), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = restoring == restore, onClick = null, enabled = !busy)
                    Text(label, modifier = Modifier.padding(start = 8.dp))
                }
            }
            OutlinedTextField(password, { password = it; clearImport(); message = null
                if (HistoryBackupCodec.validPassword(it)) invalidPassword = false
                if (it == confirmation) mismatchedConfirmation = false
            }, colors = vipiTextFieldColors(), isError = invalidPassword, label = { Text(stringResource(if (restoring) R.string.ui_3e39703b6e87 else R.string.backup_new_password)) },
                supportingText = { Text(stringResource(passwordFeedback), style = MaterialTheme.typography.bodyMedium) },
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth().focusRequester(passwordFocus).bringIntoViewRequester(passwordIntoView).testTag("backup-password"))
            if (!restoring) OutlinedTextField(confirmation, { confirmation = it
                if (password == it) mismatchedConfirmation = false
            }, colors = vipiTextFieldColors(), isError = mismatchedConfirmation,
                supportingText = { if (mismatchedConfirmation) Text(stringResource(R.string.backup_password_mismatch), style = MaterialTheme.typography.bodyMedium) }, label = { Text(stringResource(R.string.ui_d63cd658184e)) },
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth().focusRequester(confirmationFocus).bringIntoViewRequester(confirmationIntoView).testTag("backup-confirmation"))
            if (!restoring) Button(onClick = {
                if (!validate(true)) return@Button
                busy = true; message = null; clearImport()
                job = scope.launch {
                    try {
                        val exportPassword = password
                        transfer.prepareExport(temporary()) { chat.exportHistory(it, exportPassword) }
                        save.launch("Vipi-chat-history.vipihistory")
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { exported?.delete(); exported = null; message = context.getString(R.string.backup_save_failed); busy = false }
                }
            }, enabled = !busy, modifier = Modifier.fillMaxWidth().testTag("backup-create")) { Text(stringResource(R.string.ui_6a6965bcf571)) }
            if (restoring) OutlinedButton(onClick = {
                if (!validate(false)) return@OutlinedButton
                busy = true; message = null; open.launch(arrayOf("application/octet-stream", "application/*"))
            }, enabled = !busy, modifier = Modifier.fillMaxWidth().testTag("backup-open")) { Text(stringResource(R.string.ui_a67f154bcb16)) }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.ui_bb1fe2470e72), style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
    summary?.let { counts -> AlertDialog(onDismissRequest = { clearImport() }, title = { Text(stringResource(R.string.ui_d42ff6022f50)) },
        text = { Text(stringResource(R.string.backup_contents, androidx.compose.ui.res.pluralStringResource(R.plurals.backup_messages, counts.summary.messages, java.text.NumberFormat.getIntegerInstance().format(counts.summary.messages)), androidx.compose.ui.res.pluralStringResource(R.plurals.backup_conversations, counts.summary.peers, java.text.NumberFormat.getIntegerInstance().format(counts.summary.peers)))) },
        dismissButton = { TextButton(onClick = { clearImport() }) { Text(stringResource(R.string.cancel_action)) } },
        confirmButton = { TextButton(onClick = {
            val file = staged ?: return@TextButton
            summary = null; busy = true
            job = scope.launch {
                try {
                    val result = chat.importHistory(file, password, counts)
                    message = context.getString(R.string.backup_restore_result, context.resources.getQuantityString(R.plurals.backup_messages, result.added, java.text.NumberFormat.getIntegerInstance().format(result.added)), context.resources.getQuantityString(R.plurals.backup_messages, result.unchanged, java.text.NumberFormat.getIntegerInstance().format(result.unchanged)))
                } catch (error: CancellationException) { throw error }
                catch (error: Exception) { failure(error) }
                finally { clearImport(); password = ""; confirmation = ""; busy = false }
            }
        }) { Text(stringResource(R.string.ui_beb6c51b9bf6)) } }) }
}
