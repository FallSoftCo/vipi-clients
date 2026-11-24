package co.fallsoft.vipi

import org.json.JSONObject
import java.util.UUID

/** Stable identity for account-local conversation preferences. Direct peers and
 * groups are deliberately namespaced: both use UUIDs, but their settings must
 * never collide. */
internal sealed interface ConversationRef {
    val storageKey: String

    data class Direct(val peer: UUID) : ConversationRef {
        override val storageKey: String = "direct:$peer"
    }

    data class Group(val groupID: UUID) : ConversationRef {
        override val storageKey: String = "group:$groupID"
    }
}

/** Encrypted, account-owned overrides for a conversation's learning language.
 * The absence of a row means "follow the account default"; clearing a row is
 * therefore a real user choice, not a temporary UI state. */
internal class ConversationLanguageStore(private val vault: MessageVault) {
    fun all(): Map<String, String> = vault.transaction {
        vault.ids(KIND).mapNotNull { key ->
            target(vault.get(KIND, key)).let { value -> value?.let { key to it } }
        }.toMap()
    }

    fun set(ref: ConversationRef, target: String) = vault.transaction {
        require(target in initialLanguages.map { it.code })
        vault.put(KIND, ref.storageKey, JSONObject().put("version", 1).put("target", target)
            .toString().toByteArray(Charsets.UTF_8))
    }

    fun clear(ref: ConversationRef) = vault.transaction { vault.remove(KIND, ref.storageKey) }

    fun clear(storageKey: String) = vault.transaction { vault.remove(KIND, storageKey) }

    private fun target(bytes: ByteArray?): String? = bytes?.let {
        runCatching {
            val row = JSONObject(it.toString(Charsets.UTF_8))
            if (row.optInt("version") != 1) null else row.optString("target").takeIf { code -> code in initialLanguages.map { it.code } }
        }.getOrNull()
    }

    private companion object { const val KIND = "conversation-language" }
}
