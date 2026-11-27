package co.fallsoft.vipi

import java.util.UUID
import org.json.JSONObject

/**
 * The journal caller validates the Signal sender device in the same transaction. Bind both target
 * ID and its author. Pre-target updates are held under a separate bounded index.
 */
internal class ConversationReactions(private val vault: MessageVault) {
    private fun key(ref: ConversationRef, target: UUID, sender: UUID) =
        "${ref.storageKey}/$target/$sender"

    private fun actorKey(ref: ConversationRef, r: MessageReaction, actor: UUID) =
        "${key(ref, r.message, r.sender)}/$actor"

    fun next(
        ref: ConversationRef,
        target: UUID,
        sender: UUID,
        device: UUID,
        emoji: String?,
    ): MessageReaction {
        require(emoji == null || ChatFeatures.validEmoji(emoji))
        val id = "${key(ref, target, sender)}/$device"
        val last = vault.get("reaction-sequence", id)?.toString(Charsets.UTF_8)?.toInt() ?: 0
        val next = Math.addExact(last, 1)
        vault.put("reaction-sequence", id, next.toString().toByteArray())
        return MessageReaction(target, sender, next, emoji)
    }

    fun record(ref: ConversationRef, r: MessageReaction, actor: UUID, device: UUID, event: UUID) {
        if (
            ref is ConversationRef.Direct &&
                (r.sender !in setOf(vault.account, ref.peer) ||
                    actor !in setOf(vault.account, ref.peer))
        )
            return
        val id = actorKey(ref, r, actor)
        val known =
            when (ref) {
                is ConversationRef.Direct -> {
                    val raw =
                        vault.get(
                            if (r.sender == vault.account) "outgoing" else "incoming",
                            r.message.toString(),
                        )
                    raw?.let(StoredChat::parse)?.let {
                        it.features.reaction == null &&
                            it.envelope.sender == r.sender &&
                            (if (r.sender == vault.account) it.envelope.recipient == ref.peer
                            else it.envelope.sender == ref.peer)
                    } == true
                }
                is ConversationRef.Group ->
                    vault
                        .get("group-message", "${ref.groupID}/${r.message}")
                        ?.let { GroupMessage.parse(GroupsStore.json(it)) }
                        ?.let {
                            it.features.reaction == null &&
                                it.sender == r.sender &&
                                it.delivery in setOf(GroupDelivery.ACCEPTED, GroupDelivery.RECEIVED)
                        } == true
            }
        val destination = if (known) "reaction" else "reaction-waiting"
        val old = vault.get(destination, id)?.let(GroupsStore::json)
        if (old != null && old.uuid("device") == device) {
            val seq = old.getInt("sequence")
            if (
                seq > r.sequence ||
                    seq == r.sequence && old.optString("event_id") >= event.toString()
            )
                return
        }
        if (!known && old == null && vault.pageIDs(destination, "", limit = 100).size >= 100) return
        val data =
            JSONObject()
                .put("event_id", event.toString())
                .put("device", device)
                .put("sequence", r.sequence)
                .put("emoji", r.emoji ?: JSONObject.NULL)
        vault.put(destination, id, GroupsStore.bytes(data))
    }

    fun resolve(ref: ConversationRef, target: UUID, sender: UUID) {
        val prefix = key(ref, target, sender) + "/"
        for (id in vault.pageIDs("reaction-waiting", prefix, limit = 100)) {
            val o = GroupsStore.json(requireNotNull(vault.get("reaction-waiting", id)))
            val actor = UUID.fromString(id.substringAfterLast('/'))
            if (
                actor == vault.account ||
                    vault.get("peer-device", actor.toString())?.toString(Charsets.UTF_8) ==
                        o.getString("device")
            ) {
                record(
                    ref,
                    MessageReaction(
                        target,
                        sender,
                        o.getInt("sequence"),
                        if (o.isNull("emoji")) null else o.getString("emoji"),
                    ),
                    actor,
                    o.uuid("device"),
                    o.optString("event_id").takeIf(String::isNotEmpty)?.let(UUID::fromString)
                        ?: UUID(0L, 0L),
                )
            }
            vault.remove("reaction-waiting", id)
        }
    }

    fun observed(
        ref: ConversationRef,
        target: UUID,
        sender: UUID,
        actor: UUID,
    ): Pair<Int, String?>? = vault.transaction {
        vault.get("reaction", "${key(ref, target, sender)}/$actor")?.let {
            val data = GroupsStore.json(it)
            data.getInt("sequence") to if (data.isNull("emoji")) null else data.getString("emoji")
        }
    }

    fun visible(ref: ConversationRef, target: UUID, sender: UUID): Map<UUID, String> =
        vault.transaction {
            vault
                .pageIDs("reaction", key(ref, target, sender) + "/", limit = 100)
                .mapNotNull { id ->
                    val data = GroupsStore.json(requireNotNull(vault.get("reaction", id)))
                    if (data.isNull("emoji")) null
                    else UUID.fromString(id.substringAfterLast('/')) to data.getString("emoji")
                }
                .toMap()
        }
}
