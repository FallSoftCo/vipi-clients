package co.fallsoft.vipi

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import co.fallsoft.vipi.core.ImmersionEngine
import co.fallsoft.vipi.core.VocabularyEntry
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import java.util.UUID

data class VipiLanguage(val code: String, val name: String, val localName: String)
val initialLanguages = listOf(
    VipiLanguage("en", "English", "English"), VipiLanguage("es", "Spanish", "Español"),
    VipiLanguage("fr", "French", "Français"), VipiLanguage("de", "German", "Deutsch"),
    VipiLanguage("it", "Italian", "Italiano"), VipiLanguage("pt", "Portuguese", "Português"),
    VipiLanguage("ja", "Japanese", "日本語"), VipiLanguage("ko", "Korean", "한국어"),
    VipiLanguage("zh", "Chinese", "中文"), VipiLanguage("ar", "Arabic", "العربية")
)
fun languageName(code: String) = initialLanguages.firstOrNull { it.code == code }?.name ?: code
enum class Appearance { SYSTEM, LIGHT, DARK }
enum class Screen { WELCOME, LANGUAGE, ACCOUNT, HOME, SETTINGS, NEW_CHAT, BOT, LANGUAGE_DOWNLOAD, CONVERSATION, PROFILE, DELETE_ACCOUNT }
enum class ReadingMode(val label: String) { IMMERSED("Immersed"), ORIGINAL("Original"), TRANSLATION("Translation") }

class VipiModel(application: Application) : AndroidViewModel(application) {
    val authentication = Authentication(application)
    internal val deletion = AccountDeletion(application, authentication)
    private val prefs = application.getSharedPreferences("preferences", 0)
    var screen by mutableStateOf(runCatching { Screen.valueOf(prefs.getString("onboardingStep", "WELCOME")!!) }.getOrDefault(Screen.WELCOME))
        private set
    var knownLanguage by mutableStateOf(prefs.getString("knownLanguage", "en")!!)
        private set
    var targetLanguage by mutableStateOf(prefs.getString("targetLanguage", "es")!!)
        private set
    var appearance by mutableStateOf(runCatching { Appearance.valueOf(prefs.getString("appearance", "SYSTEM")!!) }.getOrDefault(Appearance.SYSTEM))
        private set
    var density by mutableDoubleStateOf(prefs.getFloat("density", .25f).toDouble())
        private set
    var modelBusy by mutableStateOf(false)
        private set
    var modelMessage by mutableStateOf<String?>(null)
        private set
    var translatedText by mutableStateOf<String?>(null)
        private set
    private val translator = LocalTranslation()
    internal var chat by mutableStateOf<ChatSession?>(null)
        private set
    var chatError by mutableStateOf<String?>(null)
        private set
    var selectedPeer by mutableStateOf<UUID?>(null)
        private set
    internal suspend fun activateChats() {
        if (deletion.active) { chat?.close(); chat = null; return }
        val userID = authentication.userID ?: return
        try {
            if (chat?.userID != userID) { chat?.close(); chat = ChatSession(getApplication(), authentication, userID) }
            navigate(Screen.HOME); chat!!.start()
            if (!deletion.active && chat?.needsProfile == true) navigate(Screen.PROFILE)
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { chatError = "Your saved conversations couldn’t be opened. Please close and reopen Vipi to try again." }
    }
    internal fun openConversation(peer: UUID) { selectedPeer = peer; navigate(Screen.CONVERSATION) }
    internal fun beginDeletion() {
        val current = requireNotNull(chat)
        check(current.profile != null || current.needsProfile)
        val account = current.profile?.id ?: UUID.randomUUID()
        deletion.begin(account, current.userID) { current.close(); chat = null; selectedPeer = null }
    }

    fun navigate(value: Screen) {
        screen = value
        if (value in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.ACCOUNT)) prefs.edit().putString("onboardingStep", value.name).apply()
    }
    fun selectKnown(code: String) {
        knownLanguage = code
        if (targetLanguage == code) selectTarget(if (code == "es") "en" else "es")
        prefs.edit().putString("knownLanguage", code).apply()
    }
    fun selectTarget(code: String) { targetLanguage = code; prefs.edit().putString("targetLanguage", code).apply() }
    fun changeAppearance(value: Appearance) { appearance = value; prefs.edit().putString("appearance", value.name).apply() }
    fun changeDensity(value: Double) { density = value; prefs.edit().putFloat("density", value.toFloat()).apply() }
    fun back() { navigate(when (screen) {
        Screen.LANGUAGE -> Screen.WELCOME
        Screen.ACCOUNT -> Screen.LANGUAGE
        Screen.LANGUAGE_DOWNLOAD -> Screen.SETTINGS
        Screen.DELETE_ACCOUNT -> if (chat?.needsProfile == true) Screen.PROFILE else Screen.SETTINGS
        else -> Screen.HOME
    }) }
    fun downloadLanguage(cellularAllowed: Boolean) = viewModelScope.launch {
        if (modelBusy) return@launch
        modelBusy = true; modelMessage = null
        try {
            translator.prepare(knownLanguage, targetLanguage, cellularAllowed)
            modelMessage = "${languageName(targetLanguage)} is ready for offline translation."
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { modelMessage = "The download couldn’t finish. Check your connection and try again." }
        finally { modelBusy = false }
    }
    fun translate(text: String) = viewModelScope.launch {
        if (modelBusy || text.isBlank()) return@launch
        modelBusy = true; modelMessage = null
        try { translatedText = translator.translate(text, knownLanguage, targetLanguage) }
        catch (error: CancellationException) { throw error }
        catch (_: Exception) { modelMessage = "Translation isn’t ready. Download this language first, then try again." }
        finally { modelBusy = false }
    }
    override fun onCleared() { translator.close(); chat?.close() }
}

val immersionPreview = ImmersionEngine().align(
    "Coffee tomorrow? I know a little place by the river.",
    "¿Café mañana? Conozco un pequeño lugar junto al río.",
    listOf(VocabularyEntry("Coffee", listOf("Café")), VocabularyEntry("tomorrow", listOf("mañana")), VocabularyEntry("river", listOf("río"))), .3
)
