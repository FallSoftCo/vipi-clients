package co.fallsoft.vipi

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import org.json.JSONObject
import java.util.UUID

/** Native main-thread coordinator; caller serializes it with ChatSession and
 * closes it before the shared account vault closes. */
internal class GroupsSession(val account: UUID, private val api: GroupsAPI, val store: GroupsStore, private val crypto: GroupsCrypto,
    private val preparePeer: suspend (UUID) -> Unit, private val needsIdentityReview: (UUID) -> Boolean) {
    private val cached = store.snapshots()
    private val activeIDs = store.activeIDs()
    var groups by mutableStateOf(cached.filter { activeIDs?.contains(it.id) != false }); private set
    var departedGroups by mutableStateOf(cached.filter { activeIDs?.contains(it.id) == false }); private set
    var invitations by mutableStateOf(emptyList<GroupInvitation>()); private set
    var busy by mutableStateOf(false); private set
    var loaded by mutableStateOf(false); private set
    var revision by mutableIntStateOf(0); private set
    var notice by mutableStateOf<String?>(null); private set
    private val membership = GroupsMembership(store.vault)
    private val controls = GroupsControlCrypto(store.vault, crypto.messagingCore)
    private var closed = false
    private val arrivals = mutableMapOf<Any, (GroupMessage) -> Unit>()
    fun observe(owner: Any, callback: (GroupMessage) -> Unit) { arrivals[owner] = callback }
    fun removeObserver(owner: Any) { arrivals.remove(owner) }
    fun group(id: UUID) = (groups + departedGroups).firstOrNull { it.id == id }
    fun isActive(id: UUID) = groups.any { it.id == id }
    fun hasMembershipConflict(id: UUID): Boolean { val observed = revision; return store.vault.transaction { store.vault.get("group-membership-conflict", id.toString()) != null } }
    fun messages(id: UUID) = if (closed) emptyList() else store.messages(id)
    fun preferences(id: UUID) = if (closed) GroupPreferences() else store.preferences(id)
    fun unread(id: UUID) = if (closed) 0 else store.unread(id, account)
    fun markRead(id: UUID, visible: Set<UUID>) {
        if (closed) return
        val old = store.preferences(id).read; val eligible = store.messages(id).filter { it.id in visible && it.sender != account && it.delivery == GroupDelivery.RECEIVED }.map { it.id }.toSet() - old
        if (eligible.isEmpty()) return; store.preferences(id) { it.copy(read = it.read + eligible) }; revision++
    }
    fun mute(id: UUID, value: Boolean) { store.preferences(id) { it.copy(muted = value) }; revision++ }
    fun draft(id: UUID, text: String) { store.preferences(id) { it.copy(draft = text) } }
    suspend fun refresh() { perform {
        val listing = api.list(); if (closed) return@perform false
        listing.groups.forEach(store::save); store.saveActiveIDs(listing.groups.map { it.id }.toSet()); departedGroups = store.snapshots().filter { cached -> listing.groups.none { it.id == cached.id } }; groups = listing.groups; invitations = listing.invitations; loaded = true; revision++; true
    } }
    private fun put(value: GroupSnapshot) { store.save(value); groups = groups.filter { it.id != value.id } + value; departedGroups = departedGroups.filter { it.id != value.id }; store.saveActiveIDs(groups.map { it.id }.toSet()); revision++ }
    private fun operation(scope: String, fields: Map<String, String>): UUID = store.vault.transaction {
        store.vault.get("group-operation", scope)?.let { bytes ->
            val o = GroupsStore.json(bytes)
            require(o.keys().asSequence().filter { it != "request_id" }.associateWith { o.getString(it) } == fields) { "An earlier change hasn’t been confirmed. Retry that exact change before making another." }
            return@transaction o.uuid("request_id")
        }
        UUID.randomUUID().also { store.vault.put("group-operation", scope, GroupsStore.bytes(JSONObject(fields).put("request_id", it))) }
    }
    private fun completed(scope: String) = store.vault.transaction { store.vault.remove("group-operation", scope) }
    private suspend fun <T> perform(action: suspend () -> T): T? {
        if (closed || busy) return null; busy = true; notice = null
        return try { action().takeUnless { closed } } catch (error: CancellationException) { throw error } catch (error: Exception) { notice = explanation(error); null } finally { busy = false }
    }
    suspend fun create(title: String): GroupSnapshot? = perform {
        val name = GroupSelection.name(title); val id = operation("create", mapOf("title" to name))
        api.create(id, name).also { membership.createdLocally(it, id); put(it); completed("create") }
    }
    suspend fun change(group: GroupSnapshot, method: String, suffix: String = "", fields: Map<String, String> = emptyMap()): Boolean = perform {
        val scope = "${group.id}$suffix$method"
        val plan = store.vault.transaction {
            store.vault.get("group-mutation", scope)?.let { bytes -> return@transaction GroupMutationPlan.parse(GroupsStore.json(bytes)).also { require(it.method == method && it.suffix == suffix && it.fields == fields) { "An earlier change hasn’t been confirmed. Retry that exact change before making another." } } }
            val previous = membership.currentInTransaction(group.id)
            if (suffix.startsWith("/members/")) require(previous?.matches(group) == true) { "Authenticated group approval is needed before changing the people." }
            GroupMutationPlan(group, UUID.randomUUID(), UUID.randomUUID(), method, suffix, fields, previous).also { store.vault.put("group-mutation", scope, GroupsStore.bytes(it.json())) }
        }
        var fanout: GroupFanout? = null
        plan.transition(account)?.let { change ->
            plan.group.members.filter { it.id != account }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
            val value = controls.prepare(plan.control, plan.group, change, System.currentTimeMillis()); fanout = value
        }
        val response = api.change(plan.group, plan.method, plan.suffix, plan.request, plan.fields, fanout)
        fanout?.let { controls.accepted(requireNotNull(response.control), it) }
        put(response.snapshot); fanout?.let(controls::reconciled); store.vault.transaction { store.vault.remove("group-mutation", scope) }; true
    } ?: false
    suspend fun invite(group: GroupSnapshot, user: UUID) = change(group, "POST", "/invitations", mapOf("user_id" to user.toString()))
    suspend fun rename(group: GroupSnapshot, title: String): Boolean { return try { change(group, "PATCH", fields = mapOf("title" to GroupSelection.name(title))) } catch (error: Exception) { notice = explanation(error); false } }
    suspend fun answer(invitation: GroupInvitation, accept: Boolean) { perform {
        val scope = "answer/${invitation.id}"; val id = operation(scope, mapOf("accept" to accept.toString(), "epoch" to invitation.epoch.toString()))
        api.answer(invitation, accept, id)?.let(::put); invitations = invitations.filter { it.id != invitation.id }; completed(scope); true
    } }
    suspend fun leave(group: GroupSnapshot): Boolean = perform {
        val scope = "leave/${group.id}"
        val plan = store.vault.transaction {
            store.vault.get("group-mutation", scope)?.let { return@transaction GroupMutationPlan.parse(GroupsStore.json(it)) }
            val previous = requireNotNull(membership.currentInTransaction(group.id)); require(previous.matches(group))
            require(previous.members.firstOrNull { it.id == account }?.role != GroupRole.OWNER || previous.members.size == 1) { "Transfer ownership to another person before leaving." }
            GroupMutationPlan(group, UUID.randomUUID(), UUID.randomUUID(), "POST", "/leave", emptyMap(), previous).also { store.vault.put("group-mutation", scope, GroupsStore.bytes(it.json())) }
        }
        val change = requireNotNull(plan.transition(account))
        plan.group.members.filter { it.id != account }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
        val fanout = controls.prepare(plan.control, plan.group, change, System.currentTimeMillis())
        controls.accepted(api.leave(plan.group, plan.request, fanout), fanout); controls.reconciled(fanout); store.vault.transaction { store.vault.remove("group-mutation", scope) }
        groups = groups.filter { it.id != group.id }; departedGroups = departedGroups.filter { it.id != group.id } + plan.group; store.saveActiveIDs(groups.map { it.id }.toSet()); revision++; true
    } ?: false
    suspend fun send(group: GroupSnapshot, text: String): Boolean {
        if (text.isBlank() || text.toByteArray(Charsets.UTF_8).size > 32768) { notice = "Write a message up to 32 KB before sending."; return false }
        val approved = membership.current(group.id)
        if (!isActive(group.id) || approved == null || !approved.matches(group)) { notice = "The people in this group haven’t been confirmed securely. Ask an existing admin to approve the change before sending."; return false }
        val message = GroupMessage(UUID.randomUUID(), group.id, group.epoch, approved.revision, account, text, System.currentTimeMillis(), GroupDelivery.QUEUED)
        store.saveMessage(message); draft(group.id, ""); revision++; retry(message); return true
    }
    suspend fun retry(message: GroupMessage) { perform {
        require(isActive(message.group) && group(message.group)?.role(account) != null) { "You’re no longer in this group. Your saved messages remain on this device." }
        val now = System.currentTimeMillis()
        if (now >= Math.addExact(message.createdAt, MessageJournal.TTL)) { store.saveMessage(message.copy(delivery = GroupDelivery.EXPIRED)); revision++; return@perform false }
        val saved = crypto.pending(message.group, message.id)
        val fanout = if (saved != null) saved else {
            val current = api.detail(message.group); put(current)
            if (current.epoch != message.epoch) { store.saveMessage(message.copy(delivery = GroupDelivery.MEMBERSHIP_CHANGED)); revision++; error("The group changed. Review Group info, then send this message again.") }
            current.members.filter { it.id != account }.forEach { member ->
                if (needsIdentityReview(member.id)) { store.saveMessage(message.copy(delivery = GroupDelivery.IDENTITY_CHANGED)); revision++; throw PeerIdentityChanged(member.id) }
                preparePeer(member.id)
            }
            crypto.prepare(message, current, now)
        }
        try { crypto.accepted(api.send(fanout), fanout) }
        catch (failure: ServiceFailure) {
            val state = when (failure.code) {
                "group_epoch_changed", "group_recipients_changed", "group_unavailable", "group_member_unavailable" -> GroupDelivery.MEMBERSHIP_CHANGED
                "recipient_identity_changed", "peer_identity_review_required" -> GroupDelivery.IDENTITY_CHANGED
                else -> message.delivery
            }
            if (state != message.delivery) { store.saveMessage(message.copy(delivery = state)); revision++ }; throw failure
        }
        revision++; true
    } }
    fun heldMessages(group: UUID): List<GroupIncoming> { val observed = revision; return if (closed) emptyList() else crypto.heldEnvelopes().filter { it.group == group } }
    fun heldControls(group: UUID): List<GroupIncoming> { val observed = revision; return if (closed) emptyList() else controls.heldEnvelopes().filter { it.group == group } }
    fun retryHeld(group: UUID) {
        try { crypto.heldEnvelopes().filter { it.group == group }.forEach { receive(it) }; controls.heldEnvelopes().filter { it.group == group }.forEach { receiveControl(it) }; revision++ }
        catch (error: Exception) { notice = explanation(error) }
    }
    fun hasRejectedApproval(group: UUID): Boolean { val observed = revision; return store.vault.transaction { store.vault.get("group-last-rejection", group.toString()) != null } }
    fun dismissRejectedApproval(group: UUID) { store.vault.transaction { store.vault.remove("group-last-rejection", group.toString()) }; revision++ }
    fun pendingCreateTitle(): String? = store.vault.transaction { store.vault.get("group-operation", "create")?.let { GroupsStore.json(it).optString("title").takeIf(String::isNotEmpty) } }
    fun pendingChanges(group: UUID): Int { val observed = revision; return store.vault.transaction { store.vault.ids("group-mutation").count { it.contains(group.toString()) } + store.vault.ids("group-join-plan").count { it.startsWith("$group/") } } }
    suspend fun resumePending(group: UUID) {
        val mutations = store.vault.transaction { store.vault.ids("group-mutation").map { GroupMutationPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-mutation", it)))) }.filter { it.group.id == group } }
        for (plan in mutations) { if (plan.suffix == "/leave") leave(plan.group) else change(plan.group, plan.method, plan.suffix, plan.fields); if (notice != null) return }
        val joins = store.vault.transaction { store.vault.ids("group-join-plan").filter { it.startsWith("$group/") }.map { GroupJoinApprovalPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-join-plan", it)))) } }
        for (plan in joins) { approveJoin(plan.group, plan.change.target); if (notice != null) return }
    }
    fun pendingApprovals(group: UUID) = controls.pending().filter { it.group == group }
    fun canBootstrap(control: GroupPendingControl) = membership.current(control.group) == null && control.transition.action == GroupControlAction.ADD && control.transition.target == account
    fun confirmBootstrap(control: GroupPendingControl) { try { controls.confirmBootstrap(control); crypto.releaseAuthorized(control.group); revision++ } catch (e: Exception) { notice = explanation(e) } }
    fun approved(group: UUID, person: UUID) = membership.current(group)?.contains(person) == true
    suspend fun approveJoin(group: GroupSnapshot, person: UUID) { perform {
        val scope = "${group.id}/$person"
        val plan = store.vault.transaction {
            store.vault.get("group-join-plan", scope)?.let { return@transaction GroupJoinApprovalPlan.parse(GroupsStore.json(it)) }
            val previous = requireNotNull(membership.currentInTransaction(group.id))
            require(!previous.contains(person) && group.members.firstOrNull { it.id == person }?.role == GroupRole.MEMBER && group.members.map { GroupApprovedPerson(it.id, it.role) }.toSet().containsAll(previous.members))
            val change = GroupRosterTransition(account, GroupControlAction.ADD, person, previous.revision, previous.revision + 1, group.epoch, previous.members, previous.members + GroupApprovedPerson(person, GroupRole.MEMBER))
            change.validated(group.id, previous, account)
            GroupJoinApprovalPlan(UUID.randomUUID(), group, change).also { store.vault.put("group-join-plan", scope, GroupsStore.bytes(it.json())) }
        }
        plan.group.members.filter { it.id != account }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
        val fanout = controls.prepare(plan.id, plan.group, plan.change, System.currentTimeMillis()); controls.accepted(api.sendControl(fanout), fanout); controls.reconciled(fanout)
        store.vault.transaction { store.vault.remove("group-join-plan", scope) }; revision++; true
    } }
    fun receiveControl(item: GroupIncoming) { check(!closed); controls.receive(item, System.currentTimeMillis()); crypto.releaseAuthorized(item.group); revision++ }
    fun receive(item: GroupIncoming): GroupMessage? {
        check(!closed)
        val duplicate = store.messages(item.group).any { it.id == item.message }
        return crypto.receive(item, System.currentTimeMillis()).also { message -> revision++; if (message != null && !duplicate && message.delivery == GroupDelivery.RECEIVED) arrivals.values.toList().forEach { it(message) }; if (message == null) notice = "A group message is held securely. Review the sender’s encryption identity before opening it." }
    }
    fun close() { closed = true; arrivals.clear(); groups = emptyList(); departedGroups = emptyList(); invitations = emptyList(); notice = null }
    companion object { fun explanation(error: Exception): String {
        if (error is PeerIdentityChanged) return "Someone’s encryption identity changed. Review their encryption details before sending."
        if (error is ServiceFailure) return when (error.code) {
            "group_epoch_changed", "group_recipients_changed" -> "The group changed. Refresh to review the people, then send your message again."
            "group_full" -> "This group already has 16 people, including its creator."
            "groups_not_available" -> "Groups aren’t available on this service yet."
            "recipient_identity_changed", "peer_identity_review_required" -> "Someone’s encryption identity changed. Review their encryption details before sending."
            "group_member_device_unavailable" -> "Someone needs to reconnect their device before this message can be sent to everyone."
            else -> "Couldn’t connect. Your messages and draft are saved on this device. Try again when you’re online."
        }
        return if (error is IllegalArgumentException || error is IllegalStateException) error.message ?: "This group couldn’t be updated. Refresh and try again." else "Couldn’t connect. Your messages and draft are saved on this device. Try again when you’re online."
    } }
}
