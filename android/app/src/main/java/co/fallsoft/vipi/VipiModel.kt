package co.fallsoft.vipi

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
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
enum class Screen { WELCOME, LANGUAGE, TUTORIAL, ACCOUNT, HOME, SETTINGS, NEW_CHAT, LANGUAGE_DOWNLOAD, CONVERSATION, PROFILE, DELETE_ACCOUNT, BACKUP, LICENSES }
enum class ReadingMode(val label: String) { IMMERSED("Immersed"), ORIGINAL("Original"), TRANSLATION("Translation") }

/** Constructor-only external boundaries for native workflow qualification. */
internal interface VipiWorkflowBoundary {
    fun transport(authentication: Authentication, userID: String): ChatTransport
    fun requestPush(context: Context, registration: Boolean)
    fun cancelPush(context: Context)
    fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents
    fun deletionTransport(authentication: Authentication): DeletionTransport? = null
    fun translationClient(): LanguageTranslation = LocalTranslation()
}

class VipiModel internal constructor(application: Application, private val translator: LanguageTranslation,
    private val workflow: VipiWorkflowBoundary?) : AndroidViewModel(application) {
    @JvmOverloads constructor(application: Application, translator: LanguageTranslation = LocalTranslation()) :
        this(application, translator, null)
    val authentication = Authentication(application)
    internal val deletion = AccountDeletion(application, authentication,
        workflow?.deletionTransport(authentication) ?: AccountDeletionService(authentication))
    private val prefs = application.getSharedPreferences("preferences", 0)
    internal var invitationUsername by mutableStateOf(prefs.getString("invitationUsername", null)?.let {
        FriendInvitationLink.username("https://api.mambovipi.app/invite/$it")
    })
        private set
    var screen by mutableStateOf(runCatching { Screen.valueOf(prefs.getString("onboardingStep", "WELCOME")!!) }.getOrDefault(Screen.WELCOME))
        private set
    var knownLanguage by mutableStateOf(prefs.getString("knownLanguage", "en")!!)
        private set
    var targetLanguage by mutableStateOf(prefs.getString("targetLanguage", "es")!!)
        private set
    var immersionMode by mutableStateOf(runCatching { ImmersionMode.valueOf(prefs.getString("immersionMode",
        if (BuildConfig.DEFAULT_FULL_IMMERSION) ImmersionMode.FULL_MESSAGES.name else ImmersionMode.NEW_WORD.name)!!) }
        .getOrDefault(if (BuildConfig.DEFAULT_FULL_IMMERSION) ImmersionMode.FULL_MESSAGES else ImmersionMode.NEW_WORD))
        private set
    fun selectImmersionMode(value: ImmersionMode) {
        prefs.edit().putString("immersionMode", value.name).apply()
        if (immersionMode == value) return
        immersionMode = value
        chat?.configureTranslations(knownLanguage, targetLanguage, workflow?.let { boundary -> boundary::translationClient }, value)
    }
    internal val replyNotificationEducation by lazy { ReplyNotificationEducation(getApplication()) }
    internal fun notificationPermissionChanged() {
        if (PushDelivery.allowed(getApplication())) requestPush(registration = true)
    }
    var appearance by mutableStateOf(runCatching { Appearance.valueOf(prefs.getString("appearance", "SYSTEM")!!) }.getOrDefault(Appearance.SYSTEM))
        private set
    var animateConversationBackground by mutableStateOf(prefs.getBoolean("animateConversationBackground", true))
        private set
    fun changeConversationAnimation(value: Boolean) {
        animateConversationBackground = value
        prefs.edit().putBoolean("animateConversationBackground", value).apply()
    }
    var density by mutableDoubleStateOf(prefs.getFloat("density", .25f).toDouble())
        private set
    var modelBusy by mutableStateOf(false)
        private set
    var modelMessage by mutableStateOf<String?>(null)
        private set
    var translatedText by mutableStateOf<String?>(null)
        private set
    private var languageReturnScreen = Screen.SETTINGS
    private var tutorialReturnScreen = Screen.ACCOUNT
    fun openTutorial() {
        tutorialReturnScreen = if (screen == Screen.LANGUAGE) Screen.ACCOUNT else Screen.SETTINGS
        navigate(Screen.TUTORIAL)
    }
    fun finishTutorial() { navigate(tutorialReturnScreen) }
    private var selectionRevision = 0L
    private var translationRevision = 0L
    internal var chat by mutableStateOf<ChatSession?>(null)
        private set
    var chatError by mutableStateOf<String?>(null)
        private set
    var selectedPeer by mutableStateOf<UUID?>(null)
        private set
    private var notificationPeer: UUID? = null
    internal suspend fun activateChats() {
        if (deletion.active) { chat?.let(DeliverySessions::delete); chat = null; return }
        val userID = authentication.userID ?: return
        try {
            val openingAccount = chat?.userID != userID
            if (openingAccount) { chat?.let(DeliverySessions::release); chat = DeliverySessions.acquire(getApplication(), authentication, userID,
                workflow?.transport(authentication, userID)) }
            // The retained model is activated again after activity recreation
            // and reauthentication. Keep this account's current conversation.
            if (openingAccount) navigate(Screen.HOME)
            chat!!.configureTranslations(knownLanguage, targetLanguage, workflow?.let { boundary -> boundary::translationClient }, immersionMode)
            chat!!.start()
            if (!deletion.active && chat?.needsProfile == true) navigate(Screen.PROFILE)
            else if (chat?.ready == true && screen == Screen.ACCOUNT) navigate(Screen.HOME)
            if (chat?.ready == true) {
                requestPush(registration = true)
                if (invitationUsername != null) navigate(Screen.NEW_CHAT)
                else openPendingNotification()
            }
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { chatError = getApplication<Application>().getString(R.string.ui_8218810809d6) }
    }
    internal fun acceptInvitation(url: String): Boolean {
        val username = FriendInvitationLink.username(url) ?: return false
        if (deletion.active) return true
        notificationPeer = null
        invitationUsername = username
        prefs.edit().putString("invitationUsername", username).apply()
        if (chat?.ready == true && chat?.userID == authentication.userID) navigate(Screen.NEW_CHAT)
        return true
    }
    private fun clearInvitation() {
        invitationUsername = null
        prefs.edit().remove("invitationUsername").apply()
    }
    internal fun openConversation(peer: UUID) { clearInvitation(); selectedPeer = peer; navigate(Screen.CONVERSATION) }
    internal fun openNotification(peer: String?) {
        notificationPeer = peer?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        if (notificationPeer != null) clearInvitation()
        if (chat?.ready == true) openPendingNotification()
    }
    private fun openPendingNotification() {
        val peer = notificationPeer; notificationPeer = null
        if (peer != null && chat?.threads?.any { it.peer == peer } == true) openConversation(peer)
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
            }, onDeviceRevoked = current::noteDeviceRevoked, onTyping = current::peerTypingEvent,
            onReceipts = current::receiptEvent, onConnected = current::eventConnected)
    internal fun beginDeletion() {
        val current = requireNotNull(chat)
        check(current.profile != null || current.needsProfile)
        val account = current.profile?.id ?: UUID.randomUUID()
        deletion.begin(account, current.userID) {
            if (workflow == null) PushDelivery.cancel(getApplication()) else workflow.cancelPush(getApplication())
            clearInvitation()
            DeliverySessions.delete(current); chat = null; selectedPeer = null
        }
    }

    fun navigate(requested: Screen) {
        val value = if (requested == Screen.HOME && screen in setOf(Screen.PROFILE, Screen.ACCOUNT) &&
            chat?.ready == true && invitationUsername != null) Screen.NEW_CHAT else requested
        if (value == Screen.LANGUAGE_DOWNLOAD && screen != value) {
            languageReturnScreen = if (screen == Screen.CONVERSATION) screen else Screen.SETTINGS
        }
        if (value != screen && (value == Screen.LANGUAGE_DOWNLOAD || screen == Screen.LANGUAGE_DOWNLOAD)) sentenceChanged()
        screen = value
        if (value in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.ACCOUNT) || (value == Screen.TUTORIAL && tutorialReturnScreen == Screen.ACCOUNT)) prefs.edit().putString("onboardingStep", value.name).apply()
    }
    fun selectKnown(code: String) {
        if (knownLanguage != code) { selectionRevision++; sentenceChanged() }
        knownLanguage = code
        if (targetLanguage == code) selectTarget(if (code == "es") "en" else "es")
        prefs.edit().putString("knownLanguage", code).apply()
        prepareSelectedPair()
    }
    fun selectTarget(code: String) {
        if (targetLanguage != code) { selectionRevision++; sentenceChanged() }
        targetLanguage = code; prefs.edit().putString("targetLanguage", code).apply()
        prepareSelectedPair()
    }
    private var pairPreparation: Job? = null
    private fun prepareSelectedPair() {
        if (knownLanguage == targetLanguage) return
        chat?.configureTranslations(knownLanguage, targetLanguage, workflow?.let { boundary -> boundary::translationClient }, immersionMode)
        pairPreparation?.cancel()
        pairPreparation = viewModelScope.launch {
            modelBusy = true; modelMessage = null
            try { translator.prepare(knownLanguage, targetLanguage, cellularAllowed = true) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { modelMessage = getApplication<Application>().getString(R.string.full_translation_failed) }
            finally { modelBusy = false }
        }
    }
    fun sentenceChanged() { translationRevision++; translatedText = null; modelMessage = null }
    fun changeAppearance(value: Appearance) { appearance = value; prefs.edit().putString("appearance", value.name).apply() }
    fun changeDensity(value: Double) { density = value; prefs.edit().putFloat("density", value.toFloat()).apply() }
    fun back() {
        if (screen == Screen.NEW_CHAT) clearInvitation()
        navigate(when (screen) {
        Screen.LANGUAGE -> Screen.WELCOME
        Screen.ACCOUNT -> Screen.TUTORIAL
        Screen.TUTORIAL -> if (tutorialReturnScreen == Screen.ACCOUNT) Screen.LANGUAGE else tutorialReturnScreen
        Screen.LANGUAGE_DOWNLOAD -> languageReturnScreen
        Screen.DELETE_ACCOUNT -> if (chat?.needsProfile == true) Screen.PROFILE else Screen.SETTINGS
        Screen.BACKUP, Screen.LICENSES -> Screen.SETTINGS
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
    override fun onCleared() { translator.close(); chat?.let(DeliverySessions::release) }
}

