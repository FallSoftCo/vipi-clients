package co.fallsoft.vipi

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONObject

/** Per-account composer metadata. Preview eligibility always follows the current text. */
internal class MessageActionDraft(
    private val vault: MessageVault?,
    private val conversation: ConversationRef,
) {
    private val restored = vault?.transaction {
        vault.get("action-compose", conversation.storageKey)?.let(GroupsStore::json)
    }
    var features by
        mutableStateOf(
            restored?.let { ChatFeatures.parse(it, it.optString("url")) } ?: ChatFeatures.EMPTY
        )
        private set

    var suppressed by mutableStateOf(restored?.optString("suppressed") ?: "")
        private set

    fun forSend(text: String) =
        features.copy(preview = features.preview?.takeIf { it.url in ChatFeatures.links(text) })

    fun quote(q: MessageQuote?) {
        features = features.copy(reply = q)
        persist()
    }

    fun preview(value: LinkSnapshot?, suppress: String = "") {
        features = features.copy(preview = value)
        suppressed = suppress
        persist()
    }

    fun clear() {
        features = ChatFeatures.EMPTY
        suppressed = ""
        persist()
    }

    private fun persist() {
        val store = vault ?: return
        store.transaction {
            if (features == ChatFeatures.EMPTY && suppressed.isEmpty())
                store.remove("action-compose", conversation.storageKey)
            else {
                val data =
                    JSONObject()
                        .put("url", features.preview?.url ?: "")
                        .put("suppressed", suppressed)
                features.write(data)
                store.put("action-compose", conversation.storageKey, GroupsStore.bytes(data))
            }
        }
    }
}

internal fun MessageVault.autoLinks(): Boolean = transaction {
    get("local", "auto-link-preview")?.firstOrNull() == 1.toByte()
}
