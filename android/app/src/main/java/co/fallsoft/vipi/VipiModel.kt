package co.fallsoft.vipi

import android.app.Application
import android.content.Context
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.PurchasesUpdatedListener
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import co.fallsoft.vipi.core.ImmersionEngine
import co.fallsoft.vipi.core.VocabularyEntry
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import java.util.UUID

data class VipiLanguage(val code: String, val name: String, val localName: String)
val initialLanguages = listOf(
    VipiLanguage("en", "English", "English"), VipiLanguage("es", "Spanish", "Español"),
    VipiLanguage("fr", "French", "Français"), VipiLanguage("de", "German", "Deutsch"),
    VipiLanguage("it", "Italian", "Italiano"), VipiLanguage("pt", "Portuguese", "Português"),
    VipiLanguage("ja", "Japanese", "日本語"), VipiLanguage("ko", "Korean", "한국어"),
    VipiLanguage("zh", "Chinese", "中文"), VipiLanguage("ar", "Arabic", "العربية"),
    VipiLanguage("sw", "Swahili", "Kiswahili")
)
fun languageName(code: String): String = if (initialLanguages.any { it.code == code })
    java.util.Locale.forLanguageTag(code).getDisplayLanguage(java.util.Locale.getDefault()) else code
enum class Appearance { SYSTEM, LIGHT, DARK }
enum class Screen { WELCOME, LANGUAGE, ACCOUNT, HOME, SETTINGS, NEW_CHAT, BOT, LANGUAGE_DOWNLOAD, CONVERSATION, PROFILE, DELETE_ACCOUNT, PLANS, BOT_PLAN, BACKUP, LICENSES }
enum class ReadingMode(val label: String) { IMMERSED("Immersed"), ORIGINAL("Original"), TRANSLATION("Translation") }

/** Constructor-only external boundaries for native workflow qualification. */
internal interface VipiWorkflowBoundary {
    fun transport(authentication: Authentication, userID: String): ChatTransport
    fun requestPush(context: Context, registration: Boolean)
    fun billingClient(context: Context, listener: PurchasesUpdatedListener): BillingClient
    fun cancelPush(context: Context)
    fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents
}

class VipiModel internal constructor(application: Application, private val translator: LanguageTranslation,
    private val workflow: VipiWorkflowBoundary?) : AndroidViewModel(application) {
    @JvmOverloads constructor(application: Application, translator: LanguageTranslation = LocalTranslation()) :
        this(application, translator, null)
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
    private var languageReturnScreen = Screen.SETTINGS
    private var selectionRevision = 0L
    private var translationRevision = 0L
    internal var chat by mutableStateOf<ChatSession?>(null)
        private set
    internal var subscriptions by mutableStateOf<Subscriptions?>(null)
        private set
    private var subscriptionUser: String? = null
    private var notificationPeer: UUID? = null
    internal var bot by mutableStateOf<BotSession?>(null)
        private set
    private var botSend: Job? = null
    var chatError by mutableStateOf<String?>(null)
        private set
    var selectedPeer by mutableStateOf<UUID?>(null)
        private set
    internal suspend fun activateChats() {
        if (deletion.active) { chat?.let(DeliverySessions::delete); chat = null; subscriptions?.close(); subscriptions = null; subscriptionUser = null; closeBot(); return }
        val userID = authentication.userID ?: run { closeBot(); return }
        try {
            if (subscriptionUser != userID) {
                closeBot()
                subscriptions?.close()
                subscriptions = Subscriptions(getApplication(), service(userID), viewModelScope, workflow?.let { boundary -> boundary::billingClient })
                subscriptionUser = userID
            }
            val openingAccount = chat?.userID != userID
            if (openingAccount) { chat?.let(DeliverySessions::release); chat = DeliverySessions.acquire(getApplication(), authentication, userID,
                workflow?.transport(authentication, userID)) }
            // The retained model is activated again after activity recreation
            // and reauthentication. Keep this account's current conversation.
            if (openingAccount) navigate(Screen.HOME)
            chat!!.start()
            if (!deletion.active && chat?.needsProfile == true) navigate(Screen.PROFILE)
            else if (chat?.ready == true && screen == Screen.ACCOUNT) navigate(Screen.HOME)
            if (chat?.ready == true) {
                requestPush(registration = true)
                openPendingNotification()
            }
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { chatError = getApplication<Application>().getString(R.string.ui_8218810809d6) }
    }
    internal fun openConversation(peer: UUID) { selectedPeer = peer; navigate(Screen.CONVERSATION) }
    internal fun openNotification(peer: String?) {
        notificationPeer = peer?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        if (chat?.ready == true) openPendingNotification()
    }
    private fun openPendingNotification() {
        val peer = notificationPeer; notificationPeer = null
        if (peer != null && chat?.threads?.any { it.peer == peer } == true) openConversation(peer)
    }
    internal fun openBot() {
        if (deletion.active) return
        val user = authentication.userID
        if (user == null) { navigate(Screen.ACCOUNT); return }
        val current = chat
        if (current == null) { navigate(Screen.HOME); return }
        if (current.userID != user) {
            // Force Home's connection/retry card rather than display a cached
            // conversation list belonging to another sign-in.
            chatError = getApplication<Application>().getString(R.string.ui_8218810809d6)
            navigate(Screen.HOME); return
        }
        if (current.needsProfile) { navigate(Screen.PROFILE); return }
        val account = current.profile?.id
        if (account == null) { navigate(Screen.HOME); return }
        // A current profile may still read saved Bot history while offline or
        // reconnecting its device. Consent/access/device checks guard sending.
        try {
            if (bot == null) bot = BotSession(getApplication(), account, service(user))
            navigate(Screen.BOT)
        } catch (_: Exception) { chatError = getApplication<Application>().getString(R.string.ui_e768f0a75223) }
    }
    /** UI navigation must not own/cancel an already dispatched Bot request. */
    internal fun sendBotMessage(): Job? {
        val user = authentication.userID ?: return null
        val current = bot ?: return null
        val plans = subscriptions ?: return null
        if (deletion.active || chat?.userID != user || chat?.profile == null ||
            plans.accessCheckState != AccessCheckState.LOADED ||
            plans.access?.bot?.verificationUnavailable == true || plans.access?.active(SubscriptionPlan.BOT_MINI) != true) return null
        botSend?.takeIf { it.isActive }?.let { return it }
        return viewModelScope.launch { current.send() }.also { botSend = it }
    }
    private fun closeBot() {
        botSend?.cancel(); botSend = null
        bot?.close(); bot = null
    }
    internal fun service(userID: String): ChatTransport = workflow?.transport(authentication, userID)
        ?: ServiceClient(authentication, userID)
    private fun requestPush(registration: Boolean) {
        if (workflow == null) PushDelivery.request(getApplication(), registration)
        else workflow.requestPush(getApplication(), registration)
    }
    internal fun foregroundEvents(scope: CoroutineScope, current: ChatSession): ForegroundInboxEvents =
        workflow?.foregroundEvents(scope, authentication, current) ?: ForegroundInboxEvents(scope,
            { rejected -> authentication.accessToken(current.userID, rejected) }, current::eventDevice, {
                current.synchronize()
                if (!current.lastSyncComplete) throw java.io.IOException("Inbox synchronization incomplete")
            }, onDeviceRevoked = current::noteDeviceRevoked)
    internal fun beginDeletion() {
        val current = requireNotNull(chat)
        check(current.profile != null || current.needsProfile)
        val account = current.profile?.id ?: UUID.randomUUID()
        deletion.begin(account, current.userID) {
            if (workflow == null) PushDelivery.cancel(getApplication()) else workflow.cancelPush(getApplication())
            DeliverySessions.delete(current); chat = null; selectedPeer = null; subscriptions?.close(); subscriptions = null; subscriptionUser = null; closeBot()
        }
    }

    fun navigate(value: Screen) {
        if (value == Screen.LANGUAGE_DOWNLOAD && screen != value) {
            languageReturnScreen = if (screen in setOf(Screen.CONVERSATION, Screen.BOT)) screen else Screen.SETTINGS
        }
        if (value != screen && (value == Screen.LANGUAGE_DOWNLOAD || screen == Screen.LANGUAGE_DOWNLOAD)) sentenceChanged()
        screen = value
        if (value == Screen.PLANS) {
            prefs.edit().putBoolean("planIntroduced", true).apply()
            if (chat?.ready == true) requestPush(registration = true)
        }
        if (value in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.ACCOUNT)) prefs.edit().putString("onboardingStep", value.name).apply()
    }
    fun selectKnown(code: String) {
        if (knownLanguage != code) { selectionRevision++; sentenceChanged() }
        knownLanguage = code
        if (targetLanguage == code) selectTarget(if (code == "es") "en" else "es")
        prefs.edit().putString("knownLanguage", code).apply()
    }
    fun selectTarget(code: String) {
        if (targetLanguage != code) { selectionRevision++; sentenceChanged() }
        targetLanguage = code; prefs.edit().putString("targetLanguage", code).apply()
    }
    fun sentenceChanged() { translationRevision++; translatedText = null; modelMessage = null }
    fun changeAppearance(value: Appearance) { appearance = value; prefs.edit().putString("appearance", value.name).apply() }
    fun changeDensity(value: Double) { density = value; prefs.edit().putFloat("density", value.toFloat()).apply() }
    fun back() { navigate(when (screen) {
        Screen.LANGUAGE -> Screen.WELCOME
        Screen.ACCOUNT -> Screen.LANGUAGE
        Screen.LANGUAGE_DOWNLOAD -> languageReturnScreen
        Screen.DELETE_ACCOUNT -> if (chat?.needsProfile == true) Screen.PROFILE else Screen.SETTINGS
        Screen.BACKUP, Screen.LICENSES -> Screen.SETTINGS
        Screen.BOT_PLAN -> if (bot != null) Screen.BOT else Screen.HOME
        else -> Screen.HOME
    }) }
    internal fun beginFallsoftLink(context: android.content.Context) {
        val current = chat ?: return
        val account = current.profile?.id ?: return
        val device = current.eventDevice() ?: return
        if (current.userID != authentication.userID || !authentication.canLinkFallsoft) return
        authentication.beginFallsoftLink(context, account, device)
    }
    fun downloadLanguage(cellularAllowed: Boolean) = viewModelScope.launch {
        if (modelBusy) return@launch
        modelBusy = true; modelMessage = null
        val revision = selectionRevision
        val source = knownLanguage; val target = targetLanguage
        try {
            translator.prepare(source, target, cellularAllowed)
            if (revision == selectionRevision) modelMessage = "${languageName(target)} is ready for offline translation."
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { if (revision == selectionRevision) modelMessage = getApplication<Application>().getString(R.string.ui_235ad6028cca) }
        finally { modelBusy = false }
    }
    fun translate(text: String) = viewModelScope.launch {
        if (modelBusy || text.isBlank()) return@launch
        modelBusy = true; modelMessage = null; translatedText = null
        val revision = ++translationRevision
        val source = knownLanguage; val target = targetLanguage
        try {
            val result = translator.translate(text, source, target)
            if (revision == translationRevision) {
                if (TranslationIntegrity.preservesIdentifiers(text, result)) translatedText = result
                else modelMessage = getApplication<Application>().getString(R.string.ui_a0c63ae7f860)
            }
        }
        catch (error: CancellationException) { throw error }
        catch (_: Exception) { if (revision == translationRevision) modelMessage = getApplication<Application>().getString(R.string.ui_3a4cae7c6a6e) }
        finally { modelBusy = false }
    }
    override fun onCleared() { translator.close(); chat?.let(DeliverySessions::release); subscriptions?.close(); closeBot() }
}

val immersionPreview = ImmersionEngine().align(
    "Coffee tomorrow? I know a little place by the river.",
    "¿Café mañana? Conozco un pequeño lugar junto al río.",
    listOf(VocabularyEntry("Coffee", listOf("Café")), VocabularyEntry("tomorrow", listOf("mañana")), VocabularyEntry("river", listOf("río"))), .3
)
