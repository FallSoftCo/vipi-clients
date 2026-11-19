package co.fallsoft.vipi

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val CLIENT_SOURCE_URL = "https://github.com/FallSoftCo/vipi-clients/releases"

private data class LicenseEntry(val title: String, val assets: List<String>)

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun LegalNoticesScreen(back: () -> Unit) {
    val context = LocalContext.current
    val uri = LocalUriHandler.current
    var selected by remember { mutableStateOf<LicenseEntry?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val entries by produceState<List<LicenseEntry>?>(null) {
        value = withContext(Dispatchers.IO) { runCatching {
            val result = mutableListOf(LicenseEntry("Vipi client · AGPL-3.0-only", listOf("licenses/vipi/NOTICE", "licenses/vipi/LICENSE")))
            val upstream = JSONObject(context.assets.open("legal/upstream/index.json").bufferedReader().use { it.readText() }).getJSONArray("licenses")
            for (index in 0 until upstream.length()) upstream.getJSONObject(index).let { row -> result.add(LicenseEntry(row.getString("coordinate"), listOf(row.getString("asset")))) }
            val bundled = JSONObject(context.assets.open("legal/third-party/index.json").bufferedReader().use { it.readText() }).getJSONArray("packages")
            val grouped = sortedMapOf<String, MutableSet<String>>()
            for (index in 0 until bundled.length()) {
                val row = bundled.getJSONObject(index); val notices = row.getJSONArray("notices")
                for (notice in 0 until notices.length()) {
                    val item = notices.getJSONObject(notice)
                    if (!item.getString("original_path").endsWith(".json")) grouped.getOrPut(row.getString("coordinate")) { linkedSetOf() }.add(item.getString("asset"))
                }
            }
            result + grouped.map { LicenseEntry(it.key, it.value.toList()) }
        }.getOrElse { error = context.getString(R.string.licenses_open_failed); emptyList() } }
    }
    val paragraphs by produceState<List<String>?>(null, selected) {
        value = selected?.let { entry -> withContext(Dispatchers.IO) {
            runCatching { entry.assets.flatMap { asset ->
                require(asset.startsWith("legal/") || asset.startsWith("licenses/vipi/"))
                context.assets.open(asset).bufferedReader().use { it.readText() }.split("\n\n").flatMap { it.chunked(4000) }
            } }.getOrElse { listOf(context.getString(R.string.licenses_open_failed)) }
        } }
    }
    fun goBack() { if (selected != null) selected = null else back() }
    BackHandler { goBack() }
    Scaffold(topBar = { TopAppBar(title = { Text(if (selected == null) stringResource(R.string.ui_2a6b4d12ccfb) else stringResource(R.string.ui_c011d6097bfb)) },
        navigationIcon = { IconButton(onClick = ::goBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) } }) }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (selected == null) {
                item { Text(stringResource(R.string.ui_cc9317e2ab2e)) }
                error?.let { item { Text(it) } }
                items(entries.orEmpty()) { entry -> Text(entry.title, Modifier.fillMaxWidth().clickable { selected = entry }.padding(vertical = 10.dp), style = MaterialTheme.typography.bodyLarge) }
                if (entries == null) item { CircularProgressIndicator() }
            } else {
                item { Text(selected!!.title, style = MaterialTheme.typography.titleMedium) }
                items(paragraphs.orEmpty()) { paragraph ->
                    if (paragraph.trim() == CLIENT_SOURCE_URL) {
                        TextButton(onClick = {
                            runCatching { uri.openUri(CLIENT_SOURCE_URL) }
                                .onFailure { error = context.getString(R.string.settings_page_open_failed) }
                        }, modifier = Modifier.heightIn(min = 48.dp)) { Text(CLIENT_SOURCE_URL) }
                    } else Text(paragraph, style = MaterialTheme.typography.bodySmall)
                }
                error?.let { item { Text(it) } }
                if (paragraphs == null) item { CircularProgressIndicator() }
            }
        }
    }
}
