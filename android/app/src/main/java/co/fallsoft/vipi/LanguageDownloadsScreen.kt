package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.launch

@Composable
internal fun LanguageDownloadsScreen(model: VipiModel) {
    val downloads = remember { LanguageDownloads() }
    DisposableEffect(downloads) { onDispose { downloads.close() } }
    Text(
        stringResource(R.string.immersion_mode_title),
        style = MaterialTheme.typography.titleLarge,
        modifier = Modifier.semantics { heading() },
    )
    listOf(
            ImmersionMode.FULL_MESSAGES to R.string.immersion_mode_full,
            ImmersionMode.NEW_WORD to R.string.immersion_mode_words_short,
        )
        .forEach { (mode, label) ->
            Row(
                Modifier.fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .selectable(
                        selected = model.immersionMode == mode,
                        role = Role.RadioButton,
                        onClick = { model.selectImmersionMode(mode) },
                    )
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                RadioButton(selected = model.immersionMode == mode, onClick = null)
                Text(stringResource(label), style = MaterialTheme.typography.bodyLarge)
            }
        }
    LanguageDownloadsContent(
        model.knownLanguage,
        model.targetLanguage,
        model::selectKnown,
        model::selectTarget,
        downloads,
    )
}

@Composable
internal fun LanguageDownloadsContent(
    source: String,
    target: String,
    onSource: (String) -> Unit,
    onTarget: (String) -> Unit,
    downloads: LanguageDownloads,
) {
    val mobileDataDescription = stringResource(R.string.ui_115f6d951109)
    val checkingDescription = stringResource(R.string.ui_66201beae1d2)
    val operationDescription = downloads.operation?.let { stringResource(it.label) }
    val voices = rememberPracticeOptions()
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
        onDispose {
            lifecycle.removeObserver(observer)
            downloads.invalidate()
        }
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(24.dp)) {
        Text(
            stringResource(R.string.ui_79a7ada4e1f1),
            style = MaterialTheme.typography.headlineMedium,
        )
        LanguageChoice(
            stringResource(R.string.already_speak),
            source,
            translationLanguages,
            !downloads.busy,
            onSource,
        )
        LanguageChoice(
            stringResource(R.string.want_learn),
            target,
            voices.targets(source, target),
            !downloads.busy,
            onTarget,
        )
        if (voices.missingVoice(target))
            Text(stringResource(R.string.voice_download_needed, languageName(target)))
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerLow,
        ) {
            Column(
                Modifier.fillMaxWidth().padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(
                    verticalAlignment = Alignment.Top,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Icon(
                        if (downloads.ready) Icons.Outlined.CheckCircle
                        else Icons.Outlined.Download,
                        null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(24.dp),
                    )
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            stringResource(R.string.ui_2e8bd38513f3),
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            when {
                                downloads.busy -> operationDescription!!
                                downloads.checking -> stringResource(R.string.languages_checking)
                                downloads.ready ->
                                    stringResource(
                                        R.string.languages_ready,
                                        languageName(source),
                                        languageName(target),
                                    )
                                downloads.installed == null ->
                                    stringResource(R.string.languages_status_unavailable)
                                else -> stringResource(R.string.languages_download_explanation)
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (downloads.busy || downloads.checking) {
                    LinearProgressIndicator(
                        Modifier.fillMaxWidth().semantics {
                            contentDescription = operationDescription ?: checkingDescription
                        }
                    )
                } else {
                    if (downloads.installed != null && !downloads.ready) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Switch(
                                checked = cellular,
                                onCheckedChange = { cellular = it },
                                modifier =
                                    Modifier.semantics {
                                        contentDescription = mobileDataDescription
                                    },
                            )
                            Text(stringResource(R.string.ui_115f6d951109))
                        }
                        Button(
                            onClick = { scope.launch { downloads.download(cellular) } },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.ui_5b80e534fb0c))
                        }
                    }
                    TextButton(onClick = { scope.launch { downloads.refresh(pair) } }) {
                        Text(stringResource(R.string.ui_f897de52ea1a))
                    }
                }
                downloads.message?.let {
                    Text(
                        stringResource(it.label),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        Text(
            stringResource(R.string.ui_52c236be01ef),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (!downloads.installed.isNullOrEmpty())
            TextButton(
                onClick = { confirmRemoval = true },
                enabled = !downloads.busy && !downloads.checking,
            ) {
                Text(
                    stringResource(R.string.ui_b8173b954090),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        Text(
            stringResource(R.string.ui_d55f942dbeea),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    if (confirmRemoval)
        AlertDialog(
            onDismissRequest = { confirmRemoval = false },
            title = { Text(stringResource(R.string.ui_048a626ab4bb)) },
            text = { Text(stringResource(R.string.ui_8ec4723d54ba)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmRemoval = false
                        scope.launch { downloads.remove() }
                    }
                ) {
                    Text(stringResource(R.string.ui_c3812fc4acb8))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmRemoval = false }) {
                    Text(stringResource(R.string.ui_f9adde8b7f6a))
                }
            },
        )
}

@Composable
private fun LanguageChoice(
    label: String,
    selected: String,
    options: List<VipiLanguage>,
    enabled: Boolean,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Box {
            OutlinedButton(
                onClick = { expanded = true },
                enabled = enabled,
                modifier = Modifier.fillMaxWidth().semantics { contentDescription = label },
            ) {
                Text(languageName(selected), Modifier.weight(1f))
                Icon(Icons.Outlined.ExpandMore, null)
            }
            LanguageChoiceMenu(
                expanded && enabled,
                selected,
                options,
                { expanded = false },
                onSelect,
            )
        }
    }
}

@Composable
internal fun LanguageChoiceMenu(
    expanded: Boolean,
    current: String,
    options: List<VipiLanguage>,
    onDismiss: () -> Unit,
    onSelect: (String) -> Unit,
    label: ((VipiLanguage) -> String)? = null,
) {
    DropdownMenu(expanded = expanded, onDismissRequest = onDismiss) {
        options.forEach { language ->
            LanguageChoiceItem(language, current, label = label) {
                onDismiss()
                if (current != language.code) onSelect(language.code)
            }
        }
    }
}

@Composable
internal fun LanguageChoiceItem(
    language: VipiLanguage,
    current: String?,
    modifier: Modifier = Modifier,
    label: ((VipiLanguage) -> String)? = null,
    onClick: () -> Unit,
) {
    val active = language.code == current
    DropdownMenuItem(
        text = {
            Text(
                label?.invoke(language) ?: "${languageName(language.code)} · ${language.localName}"
            )
        },
        modifier = modifier.semantics { selected = active },
        trailingIcon =
            if (active) {
                { Icon(Icons.Outlined.CheckCircle, null) }
            } else null,
        onClick = onClick,
    )
}
