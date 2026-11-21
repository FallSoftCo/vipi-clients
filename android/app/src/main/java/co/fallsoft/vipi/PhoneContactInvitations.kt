package co.fallsoft.vipi

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.provider.Settings
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal data class InviteAddress(val email: Boolean, val value: String)
private data class PhoneInvitee(val id: Long, val name: String, val addresses: List<InviteAddress>)
internal fun friendInviteText(context: Context, username: String) =
    context.getString(R.string.invite_share_text, username, "https://api.mambovipi.app/invite/$username")

internal fun addressedInvitation(address: InviteAddress, text: String): Intent {
    val to = Uri.encode(address.value, if (address.email) "@+" else "+")
    return if (address.email) Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:$to?body=${Uri.encode(text)}"))
        .putExtra(Intent.EXTRA_EMAIL, arrayOf(address.value)).putExtra(Intent.EXTRA_TEXT, text)
    else Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$to")).putExtra("sms_body", text)
}

private fun readInvitees(context: Context): List<PhoneInvitee> {
    val phone = ContactsContract.CommonDataKinds.Phone.CONTENT_ITEM_TYPE
    val email = ContactsContract.CommonDataKinds.Email.CONTENT_ITEM_TYPE
    val names = mutableMapOf<Long, String>()
    val targets = linkedMapOf<Long, MutableSet<InviteAddress>>()
    val fields = arrayOf(ContactsContract.Data.CONTACT_ID, ContactsContract.Data.DISPLAY_NAME_PRIMARY,
        ContactsContract.Data.MIMETYPE, ContactsContract.Data.DATA1)
    context.contentResolver.query(ContactsContract.Data.CONTENT_URI, fields,
        "${ContactsContract.Data.MIMETYPE} IN (?, ?)", arrayOf(phone, email),
        "${ContactsContract.Data.DISPLAY_NAME_PRIMARY} COLLATE LOCALIZED ASC, ${ContactsContract.Data.CONTACT_ID} ASC")?.use { cursor ->
        while (cursor.moveToNext()) {
            val id = cursor.getLong(0)
            val address = cursor.getString(3)?.trim()?.takeIf(String::isNotEmpty) ?: continue
            names[id] = cursor.getString(1)?.trim()?.takeIf(String::isNotEmpty) ?: address
            targets.getOrPut(id) { linkedSetOf() }.add(InviteAddress(cursor.getString(2) == email, address))
        }
    } ?: error("contacts_provider_unavailable")
    return targets.map { (id, addresses) -> PhoneInvitee(id, names.getValue(id), addresses.toList()) }
}

@Composable internal fun PhoneContactInvitations(username: String, dismiss: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val permission = Manifest.permission.READ_CONTACTS
    fun allowed() = ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
    var granted by remember { mutableStateOf(allowed()) }
    val activity = LocalActivity.current
    // Only the system-permission request history is retained. Contact rows,
    // addresses, search terms and selected recipients exist only in this view.
    val history = remember(context) { context.getSharedPreferences("phone-contact-permission", Context.MODE_PRIVATE) }
    var denied by remember { mutableStateOf(!granted && history.getBoolean("requested", false)) }
    var wasGranted by remember { mutableStateOf(granted) }
    var resume by remember { mutableIntStateOf(0) }
    var active by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    var people by remember { mutableStateOf<List<PhoneInvitee>?>(null) }
    var error by remember { mutableStateOf<Int?>(null) }
    var selected by remember { mutableStateOf<PhoneInvitee?>(null) }
    var query by remember { mutableStateOf("") }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { result ->
        granted = result; denied = !result; wasGranted = result || wasGranted
    }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    active = true; granted = allowed(); wasGranted = wasGranted || granted; resume++
                    if (!granted && wasGranted) denied = true
                }
                Lifecycle.Event.ON_STOP -> { active = false; people = null; selected = null; query = "" }
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(granted, active, resume) {
        people = null
        if (active && granted && allowed()) {
            try {
                val result = withContext(Dispatchers.IO) { readInvitees(context) }
                if (allowed()) { people = result; error = null } else { granted = false; denied = true }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: SecurityException) { granted = false; denied = true; selected = null }
            catch (_: Exception) { error = R.string.phone_contacts_read_error }
        }
    }
    if (!granted) {
        val settings = denied && activity?.shouldShowRequestPermissionRationale(permission) == false
        AlertDialog(onDismissRequest = dismiss,
            title = { Text(stringResource(if (denied) R.string.phone_contacts_denied else R.string.phone_contacts_title)) },
            text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.phone_contacts_explain))
                PrivacyPromise()
                if (denied) Text(stringResource(R.string.phone_contacts_denied_detail))
            } },
            confirmButton = { TextButton(onClick = {
                if (settings) context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}")))
                else { history.edit().putBoolean("requested", true).apply(); launcher.launch(permission) }
            }) { Text(stringResource(if (settings) R.string.settings_title else R.string.continue_action)) } },
            dismissButton = { TextButton(onClick = dismiss) { Text(stringResource(R.string.notification_reply_later)) } })
        return
    }
    fun draft(address: InviteAddress) {
        selected = null
        if (!allowed()) { people = null; query = ""; granted = false; denied = true; return }
        try { context.startActivity(addressedInvitation(address, friendInviteText(context, username))); error = null }
        catch (_: android.content.ActivityNotFoundException) { error = R.string.phone_no_draft }
    }
    Dialog(onDismissRequest = dismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.new_chat_phone_contacts), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                    TextButton(onClick = dismiss) { Text(stringResource(R.string.nav_back)) }
                }
                OutlinedTextField(query, { query = it }, singleLine = true, label = { Text(stringResource(R.string.phone_contacts_search)) },
                    modifier = Modifier.fillMaxWidth().testTag("phone-invite-search"))
                error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
                val rows = people
                if (rows == null && error == null) CircularProgressIndicator()
                else if (rows != null) {
                    val term = query.trim()
                    val matches = remember(rows, term) { rows.filter { person ->
                        person.name.contains(term, true) || person.addresses.any { it.value.contains(term, true) }
                    } }
                    if (matches.isEmpty()) Text(stringResource(R.string.phone_contacts_empty))
                    LazyColumn(Modifier.fillMaxWidth().weight(1f)) {
                        items(matches, key = { it.id }) { person ->
                            Column(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button) {
                                if (person.addresses.size == 1) draft(person.addresses.single()) else selected = person
                            }.padding(vertical = 8.dp)) {
                                Text(person.name, style = MaterialTheme.typography.bodyLarge)
                                Text(person.addresses.joinToString(" · ") { it.value }, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
    }
    selected?.let { person ->
        AlertDialog(onDismissRequest = { selected = null }, title = { Text(person.name) },
            text = { LazyColumn { items(person.addresses.size) { index ->
                val address = person.addresses[index]
                TextButton(onClick = { draft(address) }) { Text(stringResource(if (address.email) R.string.phone_email_to else R.string.phone_text_to, address.value)) }
            } } }, confirmButton = { TextButton(onClick = { selected = null }) { Text(stringResource(android.R.string.cancel)) } })
    }
}
