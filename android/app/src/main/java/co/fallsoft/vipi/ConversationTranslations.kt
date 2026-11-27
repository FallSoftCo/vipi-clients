package co.fallsoft.vipi

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Owns language overrides, the active translator and replay eligibility for one chat session. */
internal class ConversationTranslations(
    private val context: Context,
    private val vault: () -> MessageVault?,
    private val isClosed: () -> Boolean,
    private val conversations: () -> List<ConversationRef>,
    private val savedMessages: (List<ConversationRef>) -> Sequence<ConversationTranslation.SavedMessage>,
) {
    var current by mutableStateOf<ConversationTranslation?>(null)
        private set
    private var translationSource by mutableStateOf("en")
    private var translationDefaultTarget by mutableStateOf("es")
    var mode = ImmersionMode.NEW_WORD
        private set
    private var translationFactory: (() -> LanguageTranslation)? = null
    private val translationOwners = mutableMapOf<String, ConversationTranslation>()
    private val replayedTranslationScopes = mutableSetOf<String>()
    private val conversationLanguages = mutableStateMapOf<String, String>()
    private var activeConversation: ConversationRef? = null
    // Publish changes when the active owner changes without changing the selected language.
    private var translationGeneration by mutableIntStateOf(0)

    fun restoreOverrides(store: MessageVault) {
        conversationLanguages.clear()
        conversationLanguages.putAll(ConversationLanguageStore(store).all())
    }

    fun historyImported() {
        replayedTranslationScopes.clear()
        refresh()
    }

    fun close() {
        closeTranslationOwners()
        conversationLanguages.clear()
        activeConversation = null
    }

    /** The source language belongs to the account. Only the target can be
     * overridden by a direct or group conversation. */
    fun targetLanguage(ref: ConversationRef): String {
        translationGeneration
        val candidate = conversationLanguages[ref.storageKey] ?: translationDefaultTarget
        if (candidate != translationSource) return candidate
        return translationDefaultTarget.takeIf { it != translationSource }
            ?: translationLanguages.first { it.code != translationSource }.code
    }

    fun usesDefaultLanguage(ref: ConversationRef): Boolean {
        translationGeneration
        return conversationLanguages[ref.storageKey] == null
    }

    fun defaultTargetLanguage(): String {
        translationGeneration
        return translationDefaultTarget
    }

    fun setConversationLanguage(ref: ConversationRef, target: String) {
        require(target in translationCodes && target != translationSource)
        val store = vault() ?: return
        ConversationLanguageStore(store).set(ref, target)
        conversationLanguages[ref.storageKey] = target
        translationGeneration++
        if (activeConversation == ref) refresh()
    }

    fun useDefaultConversationLanguage(ref: ConversationRef) {
        val store = vault() ?: return
        ConversationLanguageStore(store).clear(ref)
        conversationLanguages.remove(ref.storageKey)
        translationGeneration++
        if (activeConversation == ref) refresh()
    }

    /** Language-pair owners are shared across conversations. An override is
     * conversation state; the expensive local translator and encrypted result
     * cache depend only on source, target and immersion mode. */
    fun translationFor(ref: ConversationRef): ConversationTranslation? {
        translationGeneration
        return translationOwner(targetLanguage(ref))
    }

    fun activateConversation(ref: ConversationRef) {
        activeConversation = ref
        refresh()
    }

    fun configure(source: String, target: String, factory: (() -> LanguageTranslation)?, mode: ImmersionMode) {
        require(source != target)
        val sourceChanged = source != translationSource
        val targetChanged = target != translationDefaultTarget
        val ownersInvalid = sourceChanged || mode != this.mode || factory !== translationFactory
        translationSource = source
        translationDefaultTarget = target
        translationFactory = factory
        this.mode = mode
        if (ownersInvalid) closeTranslationOwners()
        if (sourceChanged) {
            val store = vault()
            val stale = conversationLanguages.filterValues { it == source }.keys.toList()
            if (store != null) stale.forEach { ConversationLanguageStore(store).clear(it) }
            stale.forEach { conversationLanguages.remove(it) }
        }
        if (ownersInvalid || targetChanged || current == null) refresh()
    }

    private fun translationOwner(target: String): ConversationTranslation? {
        if (isClosed() || target == translationSource) return null
        val store = vault() ?: return null
        return synchronized(translationOwners) {
            translationOwners[target] ?: ConversationTranslation(
                context,
                translationSource,
                target,
                FullMessageTranslationStore(store),
                translator = translationFactory?.invoke() ?: LocalTranslation(),
                mode = mode,
            ).also { translationOwners[target] = it }
        }
    }

    private fun closeTranslationOwners() {
        synchronized(translationOwners) {
            translationOwners.values.forEach { it.close() }
            translationOwners.clear()
        }
        replayedTranslationScopes.clear()
        current = null
        translationGeneration++
    }

    fun refresh() {
        if (isClosed()) return
        val ref = activeConversation
        val owner = if (ref != null) translationOwner(targetLanguage(ref)) else translationOwner(translationDefaultTarget)
        current = owner
        translationGeneration++
        if (owner == null) return
        val refs = ref?.let(::listOf) ?: conversations().filter { targetLanguage(it) == owner.target }
        if (refs.isEmpty()) return
        val scope = owner.target + ":" + refs.joinToString(",") { it.storageKey }
        if (!replayedTranslationScopes.add(scope)) return
        owner.replaySaved { savedMessages(refs) }
    }
}
