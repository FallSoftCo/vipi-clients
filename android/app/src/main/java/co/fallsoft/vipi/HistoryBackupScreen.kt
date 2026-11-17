package co.fallsoft.vipi

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel

/** In-memory only across rotation; secrets never enter saved-state bundles. */
internal class HistoryBackupModel : ViewModel() {
    var password by mutableStateOf("")
    var confirmation by mutableStateOf("")
    var busy by mutableStateOf(false)
    var message by mutableStateOf<String?>(null)
    var summary by mutableStateOf<HistoryBackupCodec.Inspection?>(null)
    var staged by mutableStateOf<File?>(null)
    var exported by mutableStateOf<File?>(null)
    var job: Job? = null
    fun clear() {
        job?.cancel(); job = null; staged?.delete(); staged = null; exported?.delete(); exported = null
        password = ""; confirmation = ""; summary = null; message = null; busy = false
    }
    override fun onCleared() { clear() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun HistoryBackupScreen(chat: ChatSession, back: () -> Unit) {
    val context = LocalContext.current
    val transfer: HistoryBackupModel = viewModel()
    val scope = transfer.viewModelScope
    var password by transfer::password
    var confirmation by transfer::confirmation
    var busy by transfer::busy
    var message by transfer::message
    var summary by transfer::summary
    var staged by transfer::staged
    var exported by transfer::exported
    var job by transfer::job
    fun temporary() = File(context.noBackupFilesDir, "history-transfer").apply { mkdirs() }
        .resolve("${UUID.randomUUID()}.vipihistory")
    fun clearImport() { staged?.delete(); staged = null; summary = null }
    fun failure(error: Exception) {
        message = if (error is HistoryBackupCodec.DifferentAccount) "This backup belongs to a different Vipi account. Sign in to that account to restore it."
        else "The backup couldn’t be opened or saved. Check the password and file, then try again."
    }
    DisposableEffect(context) { onDispose {
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
                message = "Your encrypted chat backup is saved. Keep its password somewhere safe."
            } catch (error: CancellationException) { throw error }
            catch (error: Exception) { failure(error) }
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
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(stringResource(R.string.ui_0541b2d9f69b), style = MaterialTheme.typography.headlineMedium)
            Text(stringResource(R.string.ui_bb1fe2470e72))
            Text(stringResource(R.string.ui_233a70befbdc), style = MaterialTheme.typography.bodyMedium)
            OutlinedTextField(password, { password = it; clearImport(); message = null }, label = { Text(stringResource(R.string.ui_3e39703b6e87)) },
                supportingText = { Text(stringResource(R.string.ui_04c8049b72ff)) },
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(confirmation, { confirmation = it }, label = { Text(stringResource(R.string.ui_d63cd658184e)) },
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                busy = true; message = null; clearImport()
                job = scope.launch {
                    var file: File? = null
                    try {
                        file = temporary(); chat.exportHistory(file, password)
                        exported = file; file = null
                        save.launch("Vipi-chat-history.vipihistory")
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { exported?.delete(); exported = null; failure(error); busy = false }
                    finally { file?.delete() }
                }
            }, enabled = !busy && HistoryBackupCodec.validPassword(password) && password == confirmation, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ui_6a6965bcf571)) }
            OutlinedButton(onClick = { busy = true; message = null; open.launch(arrayOf("application/octet-stream", "application/*")) },
                enabled = !busy && HistoryBackupCodec.validPassword(password), modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ui_a67f154bcb16)) }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
    }
    summary?.let { counts -> AlertDialog(onDismissRequest = { clearImport() }, title = { Text(stringResource(R.string.ui_d42ff6022f50)) },
        text = { Text("This backup contains ${counts.summary.messages} messages and ${counts.summary.peers} conversations. Matching messages are kept once. Existing conversations and messaging security stay in place.") },
        dismissButton = { TextButton(onClick = { clearImport() }) { Text(stringResource(R.string.cancel_action)) } },
        confirmButton = { TextButton(onClick = {
            val file = staged ?: return@TextButton
            summary = null; busy = true
            job = scope.launch {
                try {
                    val result = chat.importHistory(file, password, counts)
                    message = "Restored ${result.added} messages. ${result.unchanged} matching messages were already saved."
                } catch (error: CancellationException) { throw error }
                catch (error: Exception) { failure(error) }
                finally { clearImport(); password = ""; confirmation = ""; busy = false }
            }
        }) { Text(stringResource(R.string.ui_beb6c51b9bf6)) } }) }
}
