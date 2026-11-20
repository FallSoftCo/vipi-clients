package co.fallsoft.vipi

import org.json.JSONObject
import java.util.UUID

/** Counts encoded recovery payloads, not total SQLite/WAL disk; never evicts existing recovery messages. */
internal class GroupsHoldBudget(private val vault: MessageVault) {
    fun reserveInTransaction(kind: String, id: String, group: UUID, bytes: Int) {
        val key = "$kind/$id"; if (vault.get("group-hold-budget", key) != null) return
        val entries = vault.ids("group-hold-budget").map { GroupsStore.json(requireNotNull(vault.get("group-hold-budget", it))) }
        val local = entries.filter { it.uuid("group") == group }
        require(bytes >= 0 && entries.size < 1024 && local.size < 128 && entries.sumOf { it.strictLong("bytes") } + bytes <= 32L * 1024 * 1024 && local.sumOf { it.strictLong("bytes") } + bytes <= 8L * 1024 * 1024) { "Saved messages need review before more can be opened. Review waiting messages in Group info, then try again." }
        vault.put("group-hold-budget", key, GroupsStore.bytes(JSONObject().put("group", group).put("bytes", bytes)))
    }
    fun releaseInTransaction(kind: String, id: String) = vault.remove("group-hold-budget", "$kind/$id")
}
