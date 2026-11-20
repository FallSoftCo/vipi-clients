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
    private val preparePeer: suspend (UUID) -> Unit, private val needsIdentityReview: (UUID) -> Boolean, private val committed: (GroupMessage) -> Unit = {}) {
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
    private val recovery = GroupsRecoveryJournal(store.vault)
    var recoveryReview by mutableStateOf<GroupRecoveryReview?>(null); private set
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
            require(store.vault.ids("group-mutation").none { it.contains(group.id.toString()) && it != scope } && store.vault.ids("group-join-plan").none { it.startsWith("${group.id}/") }) { "Resume the saved group change before making another." }
            val previous = membership.currentInTransaction(group.id)
            if (suffix.startsWith("/members/")) require(previous?.matches(group) == true) { "Authenticated group approval is needed before changing the people." }
            GroupMutationPlan(group, UUID.randomUUID(), UUID.randomUUID(), method, suffix, fields, previous, api.originalDeviceID).also { store.vault.put("group-mutation", scope, GroupsStore.bytes(it.json())) }
        }
        checkOriginalDevice(plan.originalDevice)
        var fanout: GroupFanout? = null
        plan.transition(account)?.let { change ->
            plan.group.members.filter { it.id != account && it.device != null }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
            val value = controls.prepare(plan.control, plan.group, change, System.currentTimeMillis()); fanout = value
        }
        rememberMutation(plan, scope, fanout)
        val response = api.change(plan.group, plan.method, plan.suffix, plan.request, plan.fields, fanout)
        completeMutation(plan, scope, fanout, response.snapshot, response.control); true
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
            require(store.vault.ids("group-mutation").none { it.contains(group.id.toString()) && it != scope } && store.vault.ids("group-join-plan").none { it.startsWith("${group.id}/") }) { "Resume the saved group change before making another." }
            val previous = requireNotNull(membership.currentInTransaction(group.id)); require(previous.matches(group))
            require(previous.members.firstOrNull { it.id == account }?.role != GroupRole.OWNER || previous.members.size == 1) { "Transfer ownership to another person before leaving." }
            GroupMutationPlan(group, UUID.randomUUID(), UUID.randomUUID(), "POST", "/leave", emptyMap(), previous, api.originalDeviceID).also { store.vault.put("group-mutation", scope, GroupsStore.bytes(it.json())) }
        }
        checkOriginalDevice(plan.originalDevice)
        val change = requireNotNull(plan.transition(account))
        plan.group.members.filter { it.id != account && it.device != null }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
        val fanout = controls.prepare(plan.control, plan.group, change, System.currentTimeMillis())
        rememberMutation(plan, scope, fanout)
        val accepted = api.leave(plan.group, plan.request, fanout)
        completeMutation(plan, scope, fanout, null, accepted); true
    } ?: false
    suspend fun send(group: GroupSnapshot, text: String): Boolean {
        if (text.isBlank() || text.toByteArray(Charsets.UTF_8).size > 32768) { notice = "Write a message up to 32 KB before sending."; return false }
        val approved = membership.current(group.id)
        if (!isActive(group.id) || approved == null || !approved.matches(group)) { notice = "The people in this group haven’t been confirmed securely. Ask an existing admin to approve the change before sending."; return false }
        val message = GroupMessage(UUID.randomUUID(), group.id, group.epoch, approved.revision, account, text, System.currentTimeMillis(), GroupDelivery.QUEUED)
        store.saveMessage(message); draft(group.id, ""); revision++; committed(message); retry(message); return true
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
    fun savedSenderName(group: UUID, person: UUID): String? = if (closed) null else store.cachedName(group, person)
    fun messageOriginal(group: UUID, id: UUID): String? = if (closed) null else messages(group).firstOrNull { it.id == id && it.delivery != GroupDelivery.WITHHELD }?.text
    fun historyForImmersion(): List<GroupMessage> = if (closed) emptyList() else (groups + departedGroups).flatMap { messages(it.id) }.filter { it.delivery != GroupDelivery.WITHHELD }.sortedWith(compareBy({ it.createdAt }, { it.renderID }))
    fun pendingReceipts() = crypto.receipts()
    fun receiptAccepted(id: UUID) = crypto.receiptAccepted(id)
    suspend fun synchronize() {
        refresh(); if (closed) return
        groups.forEach { retryHeld(it.id) }
        val queued = groups.flatMap { messages(it.id) }.filter { it.sender == account && it.delivery == GroupDelivery.QUEUED }.sortedBy { it.createdAt }.take(50)
        queued.forEach { if (!closed) retry(it) }
    }
    fun heldMessages(group: UUID): List<GroupIncoming> { val observed = revision; return if (closed) emptyList() else crypto.heldEnvelopes().filter { it.group == group } }
    fun heldControls(group: UUID): List<GroupIncoming> { val observed = revision; return if (closed) emptyList() else controls.heldEnvelopes().filter { it.group == group } }
    fun retryHeld(group: UUID) {
        try { crypto.heldEnvelopes().filter { it.group == group }.forEach { receive(it) }; controls.heldEnvelopes().filter { it.group == group }.forEach { receiveControl(it) }; revision++ }
        catch (error: Exception) { notice = explanation(error) }
    }
    fun hasRejectedApproval(group: UUID): Boolean { val observed = revision; return store.vault.transaction { store.vault.get("group-last-rejection", group.toString()) != null } }
    fun dismissRejectedApproval(group: UUID) { store.vault.transaction { store.vault.remove("group-last-rejection", group.toString()) }; revision++ }
    fun pendingCreateTitle(): String? = store.vault.transaction { store.vault.get("group-operation", "create")?.let { GroupsStore.json(it).optString("title").takeIf(String::isNotEmpty) } }
    fun pendingDescriptions(group: UUID, people: List<ChatProfile>): List<String> {
        val plans = store.vault.transaction { store.vault.ids("group-mutation").map { GroupMutationPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-mutation", it)))) }.filter { it.group.id == group } }
        val joins = store.vault.transaction { store.vault.ids("group-join-plan").filter { it.startsWith("$group/") }.map { GroupJoinApprovalPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-join-plan", it)))) } }
        fun name(id: UUID) = people.firstOrNull { it.id == id }?.displayName ?: savedSenderName(group, id) ?: "this person"
        return plans.map { plan -> when {
            plan.suffix == "/leave" -> "Leave ${plan.group.title}"
            "title" in plan.fields -> "Rename ${plan.group.title} to ${plan.fields["title"]}"
            plan.suffix.startsWith("/members/") -> { val person = UUID.fromString(plan.suffix.removePrefix("/members/")); if (plan.method == "DELETE") "Remove ${name(person)} from the group" else if (plan.fields["role"] == "owner") "Make ${name(person)} the group owner" else "Change ${name(person)}’s admin role" }
            "user_id" in plan.fields -> "Invite ${name(UUID.fromString(plan.fields.getValue("user_id")))} to the group"
            else -> "Cancel a group invitation"
        } } + joins.map { "Approve ${name(it.change.target)} joining the group" }
    }
    fun pendingChanges(group: UUID): Int { val observed = revision; return store.vault.transaction { store.vault.ids("group-mutation").count { it.contains(group.toString()) } + store.vault.ids("group-join-plan").count { it.startsWith("$group/") } } }
    suspend fun resumePending(group: UUID) {
        val mutations = store.vault.transaction { store.vault.ids("group-mutation").map { GroupMutationPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-mutation", it)))) }.filter { it.group.id == group } }
        for (plan in mutations) { if (plan.suffix == "/leave") leave(plan.group) else change(plan.group, plan.method, plan.suffix, plan.fields); if (notice != null) return }
        val joins = store.vault.transaction { store.vault.ids("group-join-plan").filter { it.startsWith("$group/") }.map { GroupJoinApprovalPlan.parse(GroupsStore.json(requireNotNull(store.vault.get("group-join-plan", it)))) } }
        for (plan in joins) { approveJoin(plan.group, plan.change.target); if (notice != null) return }
    }
    fun pendingApprovals(group: UUID) = controls.pending().filter { it.group == group }
    fun canBootstrap(control: GroupPendingControl) = membership.current(control.group) == null && control.transition.action == GroupControlAction.ADD && control.transition.target == account
    fun confirmBootstrap(control: GroupPendingControl) { try { controls.confirmBootstrap(control); crypto.releaseAuthorized(control.group).forEach(committed); revision++ } catch (e: Exception) { notice = explanation(e) } }
    fun approved(group: UUID, person: UUID) = membership.current(group)?.contains(person) == true
    suspend fun approveJoin(group: GroupSnapshot, person: UUID) { perform {
        val scope = "${group.id}/$person"
        val plan = store.vault.transaction {
            store.vault.get("group-join-plan", scope)?.let { return@transaction GroupJoinApprovalPlan.parse(GroupsStore.json(it)) }
            require(store.vault.ids("group-mutation").none { it.contains(group.id.toString()) } && store.vault.ids("group-join-plan").none { it.startsWith("${group.id}/") && it != scope }) { "Resume the saved group change before making another." }
            val previous = requireNotNull(membership.currentInTransaction(group.id))
            require(!previous.contains(person) && group.members.firstOrNull { it.id == person }?.role == GroupRole.MEMBER && group.members.map { GroupApprovedPerson(it.id, it.role) }.toSet().containsAll(previous.members))
            val change = GroupRosterTransition(account, GroupControlAction.ADD, person, previous.revision, previous.revision + 1, group.epoch, previous.members, previous.members + GroupApprovedPerson(person, GroupRole.MEMBER))
            change.validated(group.id, previous, account)
            GroupJoinApprovalPlan(UUID.randomUUID(), group, change, api.originalDeviceID).also { store.vault.put("group-join-plan", scope, GroupsStore.bytes(it.json())) }
        }
        checkOriginalDevice(plan.originalDevice)
        plan.group.members.filter { it.id != account && it.device != null }.forEach { if (needsIdentityReview(it.id)) throw PeerIdentityChanged(it.id); preparePeer(it.id) }
        val fanout = controls.prepare(plan.id, plan.group, plan.change, System.currentTimeMillis())
        plan.originalDevice?.let { recovery.remember(PreparedGroupOperation.capture(plan.group.id, plan.id, "control", plan.group.epoch, it, originalControl = fanout), "group-join-plan", scope, fanout) }
        completeJoin(plan, scope, fanout, api.sendControl(fanout)); true
    } }
    fun receiveControl(item: GroupIncoming) { check(!closed); controls.receive(item, System.currentTimeMillis()); crypto.releaseAuthorized(item.group).forEach(committed); revision++ }
    fun receive(item: GroupIncoming): GroupMessage? {
        check(!closed)
        val duplicate = store.messages(item.group).any { it.id == item.message }
        return crypto.receive(item, System.currentTimeMillis()).also { message -> revision++; if (message != null && !duplicate && message.delivery == GroupDelivery.RECEIVED) { committed(message); arrivals.values.toList().forEach { it(message) } }; if (message == null) notice = "A group message is held securely. Review the sender’s encryption identity before opening it." }
    }
    private fun checkOriginalDevice(original: UUID?) {
        require(original == null || original == api.originalDeviceID) { "Your device changed. Check the saved change before continuing; its original encryption is still retained." }
    }
    private fun rememberMutation(plan: GroupMutationPlan, scope: String, fanout: GroupFanout?) {
        val device = plan.originalDevice ?: return // Legacy: exact retry only.
        val (action, fields) = when {
            plan.suffix == "/leave" -> "leave" to emptyMap()
            plan.suffix.isEmpty() && plan.method == "PATCH" -> "rename" to mapOf("title" to plan.fields.getValue("title"))
            plan.suffix == "/invitations" && plan.method == "POST" -> "invite" to mapOf("target_id" to plan.fields.getValue("user_id"))
            plan.suffix.startsWith("/members/") && plan.method == "DELETE" -> "remove" to mapOf("target_id" to UUID.fromString(plan.suffix.removePrefix("/members/")).toString())
            plan.suffix.startsWith("/members/") && plan.method == "PATCH" -> "role" to mapOf("target_id" to UUID.fromString(plan.suffix.removePrefix("/members/")).toString(), "role" to plan.fields.getValue("role"))
            plan.suffix.startsWith("/invitations/") && plan.method == "DELETE" -> "cancel-invite" to mapOf("invite_id" to UUID.fromString(plan.suffix.removePrefix("/invitations/")).toString())
            else -> error("This saved change cannot be cancelled safely. Retry its exact original operation.")
        }
        recovery.remember(PreparedGroupOperation.capture(plan.group.id, plan.request, action, plan.group.epoch, device, fields, fanout), "group-mutation", scope, fanout)
    }
    private fun reloadSavedGroups() {
        val values = store.snapshots(); val active = store.activeIDs()
        groups = values.filter { active?.contains(it.id) != false }
        departedGroups = values.filter { active?.contains(it.id) == false }; revision++
    }
    /** Removing a prepared control and its parent plan is one commit. A crash
     * cannot leave the old plan around to encrypt a new fanout under its old ID. */
    private fun completeMutation(plan: GroupMutationPlan, scope: String, fanout: GroupFanout?, snapshot: GroupSnapshot?, accepted: JSONObject?) {
        val active = groups.map { it.id }.toSet().let { if (plan.suffix == "/leave") it - plan.group.id else it }
        store.vault.transaction {
            fanout?.let { controls.acceptedInTransaction(requireNotNull(accepted), it) }
            snapshot?.let { value ->
                val saved = store.snapshotsInTransaction().firstOrNull { it.id == value.id }
                if (saved == null || value.epoch >= saved.epoch) store.saveInTransaction(value)
            }
            store.saveActiveIDsInTransaction(active) // Never reactivate a departed group from an old saved result.
            fanout?.let(controls::reconciledInTransaction)
            store.vault.remove("group-mutation", scope)
            recovery.completedInTransaction(plan.group.id, plan.request)
        }
        reloadSavedGroups()
    }
    private fun completeJoin(plan: GroupJoinApprovalPlan, scope: String, fanout: GroupFanout, accepted: JSONObject) {
        store.vault.transaction {
            controls.acceptedInTransaction(accepted, fanout); controls.reconciledInTransaction(fanout)
            store.vault.remove("group-join-plan", scope); recovery.completedInTransaction(plan.group.id, plan.id)
        }
        revision++
    }
    fun recoveryAvailable(group: UUID): Boolean { val observed = revision; return !closed && recovery.entries(group).isNotEmpty() }
    fun recoveryCancelled(group: UUID): Boolean { val observed = revision; return !closed && recovery.entries(group).any { it.cancelled } }
    fun dismissRecoveryReview() { recoveryReview = null }
    suspend fun checkSavedChange(group: UUID) { perform {
        val entry = recovery.entries(group).singleOrNull() ?: error("This earlier change has no safely captured original device. Retry its exact operation; it cannot be discarded automatically.")
        val outcome = entry.receipt?.let { entry.original.resolution(JSONObject(it)) } ?: api.resolve(entry.original)
        recovery.record(entry, outcome); revision++
        when (outcome) {
            is GroupOperationResolution.Cancelled -> {
                val current = api.detail(group)
                if (!closed) recoveryReview = GroupRecoveryReview(recovery.entries(group).single(), current)
            }
            is GroupOperationResolution.Admitted -> {
                val result = JSONObject(outcome.originalResult)
                val link = entry.links.first()
                when (link.kind) {
                    "group-mutation" -> {
                        val plan = store.vault.transaction { GroupMutationPlan.parse(GroupsStore.json(requireNotNull(store.vault.get(link.kind, link.id)))) }
                        require(plan.group.id == group && plan.request == entry.original.request)
                        val fanout = entry.links.firstOrNull { it.kind == "group-control-outgoing" }?.let { control -> store.vault.transaction { GroupFanout.parse(GroupsStore.json(requireNotNull(store.vault.get(control.kind, control.id)))) } }
                        if (plan.suffix == "/leave") {
                            require(result.getBoolean("left")); completeMutation(plan, link.id, fanout, null, result.optJSONObject("control_acceptance"))
                        } else completeMutation(plan, link.id, fanout, GroupSnapshot.parse(result), result.optJSONObject("control_acceptance"))
                    }
                    "group-join-plan" -> {
                        val plan = store.vault.transaction { GroupJoinApprovalPlan.parse(GroupsStore.json(requireNotNull(store.vault.get(link.kind, link.id)))) }
                        require(plan.group.id == group && plan.id == entry.original.request)
                        val control = entry.links.single { it.kind == "group-control-outgoing" }
                        val fanout = store.vault.transaction { GroupFanout.parse(GroupsStore.json(requireNotNull(store.vault.get(control.kind, control.id)))) }
                        completeJoin(plan, link.id, fanout, result)
                    }
                    else -> error("Unrecognized original group change. Its journal is retained.")
                }
                notice = "The service had already applied this exact saved change. Its original outcome is now reconciled."
            }
        }; true
    } }
    suspend fun confirmCancelledChange() { perform {
        val review = requireNotNull(recoveryReview)
        val current = api.detail(review.current.id)
        if (current != review.current) {
            recoveryReview = GroupRecoveryReview(review.entry, current)
            error("The group changed again. Review the updated people before closing the saved change.")
        }
        recovery.archiveCancelled(review.entry, current) { store.saveInTransaction(current) }
        recoveryReview = null; reloadSavedGroups()
        notice = "The earlier change was cancelled and saved privately. You can now choose a new change with a new request."
        true
    } }
    fun close() { closed = true; recoveryReview = null; arrivals.clear(); groups = emptyList(); departedGroups = emptyList(); invitations = emptyList(); notice = null }
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
