package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.launch

@Composable internal fun LanguageDownloadsScreen(model: VipiModel) {
    val downloads = remember { LanguageDownloads() }
    DisposableEffect(downloads) { onDispose { downloads.close() } }
    LanguageDownloadsContent(model.knownLanguage, model.targetLanguage, model::selectKnown, model::selectTarget, downloads)
}

@Composable internal fun LanguageDownloadsContent(source: String, target: String,
    onSource: (String) -> Unit, onTarget: (String) -> Unit, downloads: LanguageDownloads) {
    val pair = DownloadPair(source, target)
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var cellular by rememberSaveable { mutableStateOf(false) }
    var confirmRemoval by remember(pair) { mutableStateOf(false) }
    LaunchedEffect(pair, downloads) { downloads.refresh(pair) }
    DisposableEffect(lifecycle, pair, downloads) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) scope.launch { downloads.refresh(pair) }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); downloads.invalidate() }
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text("Your languages", style = MaterialTheme.typography.headlineMedium)
        LanguageChoice("I already speak", source, initialLanguages, !downloads.busy, onSource)
        LanguageChoice("I’m picking up", target, initialLanguages.filter { it.code != source }, !downloads.busy, onTarget)
        Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surfaceContainerLow) {
            Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(if (downloads.ready) Icons.Outlined.CheckCircle else Icons.Outlined.Download, null,
                        tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(24.dp))
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Offline translation", fontWeight = FontWeight.SemiBold)
                        Text(when {
                            downloads.busy -> downloads.operation!!
                            downloads.checking -> "Checking this phone…"
                            downloads.ready -> "${languageName(source)} and ${languageName(target)} are ready for offline translation."
                            downloads.installed == null -> "Download status isn’t available."
                            else -> "Download your languages to translate on this phone, even offline."
                        }, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if (downloads.busy || downloads.checking) {
                    LinearProgressIndicator(Modifier.fillMaxWidth().semantics {
                        contentDescription = downloads.operation ?: "Checking downloads"
                    })
                } else {
                    if (downloads.installed != null && !downloads.ready) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Switch(checked = cellular, onCheckedChange = { cellular = it },
                                modifier = Modifier.semantics { contentDescription = "Allow mobile data" })
                            Text("Allow mobile data")
                        }
                        Button(onClick = { scope.launch { downloads.download(cellular) } }, modifier = Modifier.fillMaxWidth()) {
                            Text("Download languages")
                        }
                    }
                    TextButton(onClick = { scope.launch { downloads.refresh(pair) } }) { Text("Check downloads") }
                }
                downloads.message?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        }
        Text("Once downloaded, translation happens on your phone. Your messages aren’t sent to a translation service.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (!downloads.installed.isNullOrEmpty()) TextButton(onClick = { confirmRemoval = true }, enabled = !downloads.busy && !downloads.checking) {
            Text("Remove translation downloads", color = MaterialTheme.colorScheme.error)
        }
        Text("Translation by Google. Translations can be imperfect.", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (confirmRemoval) AlertDialog(onDismissRequest = { confirmRemoval = false }, title = { Text("Remove downloads?") },
        text = { Text("You’ll need to download these languages again before translating offline. Your conversations stay on this phone.") },
        confirmButton = { TextButton(onClick = { confirmRemoval = false; scope.launch { downloads.remove() } }) { Text("Remove") } },
        dismissButton = { TextButton(onClick = { confirmRemoval = false }) { Text("Keep downloads") } })
}

@Composable private fun LanguageChoice(label: String, selected: String, options: List<VipiLanguage>, enabled: Boolean, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Box {
            OutlinedButton(onClick = { expanded = true }, enabled = enabled, modifier = Modifier.fillMaxWidth()
                .semantics { contentDescription = label }) {
                Text(languageName(selected), Modifier.weight(1f)); Icon(Icons.Outlined.ExpandMore, null)
            }
            DropdownMenu(expanded = expanded && enabled, onDismissRequest = { expanded = false }) {
                options.forEach { language -> DropdownMenuItem(text = { Text("${language.name} · ${language.localName}") },
                    onClick = { expanded = false; onSelect(language.code) }) }
            }
        }
    }
}
