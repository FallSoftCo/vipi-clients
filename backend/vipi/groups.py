"""Opt-in group roster authority and atomic opaque pairwise fanout.

No crypto is implemented here. Callers own transactions. User locks precede
all group locks; group membership is rechecked after those locks are obtained.
"""
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, delete, or_, select, update

from .db import (Block, ChatGroup, Device, GroupInvitation, GroupMember,
                 GroupMessage, GroupOperation, GroupCancellation, PendingMessage, User)
from .delivery import DeliveryError, Envelope, accept, fingerprint, utc

CAP = 16


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clean_title(title):
    title = title.strip()
    if not title or len(title) > 80 or any(unicodedata.category(c).startswith("C") for c in title):
        raise DeliveryError("invalid_group_title")
    return title


async def members(session, group_id):
    return (await session.scalars(select(GroupMember).where(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at, GroupMember.user_id).execution_options(populate_existing=True))).all()


async def lock_group(session, group_id, actor_id, *, extra=(), allow_closed=False):
    before = {m.user_id for m in await members(session, group_id)}
    user_ids = sorted(before | {actor_id} | set(extra))
    users = (await session.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.id)
        .with_for_update().execution_options(populate_existing=True))).all()
    actor = next((u for u in users if u.id == actor_id), None)
    if not actor or actor.deleted or actor.suspended:
        raise DeliveryError("account_unavailable", 404)
    group = (await session.scalars(select(ChatGroup).where(ChatGroup.id == group_id)
        .with_for_update().execution_options(populate_existing=True))).one_or_none()
    if not group or (group.state != "active" and not allow_closed):
        raise DeliveryError("group_unavailable", 404)
    roster = await members(session, group_id)
    if {m.user_id for m in roster} != before:
        raise DeliveryError("group_epoch_changed", 409)
    return group, roster, users


def member_for(roster, user_id):
    member = next((m for m in roster if m.user_id == user_id), None)
    if not member:
        raise DeliveryError("group_unavailable", 404)
    return member


def admin_for(roster, user_id):
    member = member_for(roster, user_id)
    if member.role not in ("owner", "admin"):
        raise DeliveryError("group_permission_denied", 403)
    return member


def epoch_matches(group, epoch):
    if group.epoch != epoch:
        raise DeliveryError("group_epoch_changed", 409)


async def blocked_pair(session, ids, *, target=None):
    query = select(Block).where(Block.blocker_id.in_(ids), Block.blocked_id.in_(ids))
    if target:
        query = query.where(or_(Block.blocker_id == target, Block.blocked_id == target))
    return (await session.execute(query)).first() is not None


async def snapshot(session, group, roster=None):
    roster = await members(session, group.id) if roster is None else roster
    ids = [m.user_id for m in roster]
    users = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}
    devices = (await session.scalars(select(Device).where(Device.user_id.in_(ids), Device.active.is_(True)).order_by(Device.id))).all()
    routes = {}
    for device in devices:
        if device.user_id in routes:
            # register_device serializes this invariant. Fail closed if legacy
            # or manually corrupted data violates the single-device protocol.
            raise DeliveryError("group_device_state_invalid", 409)
        routes[device.user_id] = device.id
    invitations = (await session.scalars(select(GroupInvitation).where(GroupInvitation.group_id == group.id,
        GroupInvitation.state == "pending").order_by(GroupInvitation.id))).all()
    return {"id": group.id, "title": group.title, "epoch": group.epoch, "state": group.state,
        "members": [{"user_id": m.user_id, "username": users[m.user_id].username,
                     "display_name": users[m.user_id].display_name, "role": m.role,
                     "joined_epoch": m.joined_epoch, "device_id": routes.get(m.user_id)} for m in roster],
        "invitations": [{"id": i.id, "user_id": i.user_id, "invited_by": i.invited_by,
                         "expires_at": utc(i.expires_at).isoformat(), "state": i.state} for i in invitations]}


async def list_groups(session, actor_id, *, now):
    groups = (await session.scalars(select(ChatGroup).join(GroupMember).where(GroupMember.user_id == actor_id,
        ChatGroup.state == "active").order_by(ChatGroup.created_at.desc(), ChatGroup.id))).all()
    invitations = (await session.execute(select(GroupInvitation, ChatGroup).join(ChatGroup).where(
        GroupInvitation.user_id == actor_id, GroupInvitation.state == "pending",
        GroupInvitation.expires_at > utc(now), ChatGroup.state == "active")
        .order_by(GroupInvitation.created_at.desc()))).all()
    return {"groups": [await snapshot(session, group) for group in groups], "invitations": [
        {"id": i.id, "group_id": g.id, "title": g.title, "invited_by": i.invited_by,
         "expires_at": utc(i.expires_at).isoformat(), "epoch": g.epoch} for i, g in invitations]}


async def notify_group(session, group_id, *, now, extra=()):
    ids = {m.user_id for m in await members(session, group_id)} | set(extra)
    await notify_users(session, ids, now=now)


async def notify_users(session, ids, *, now):
    from .events import notify
    from .push import enqueue
    devices = (await session.scalars(select(Device).where(Device.user_id.in_(ids), Device.active.is_(True)).order_by(Device.id))).all()
    for device in devices:
        await notify(session, device.id)
        await enqueue(session, device.id, utc(now), utc(now) + timedelta(hours=72), group_event=True)


async def create(session, *, actor_id, group_id, title, now):
    title = clean_title(title)
    user = (await session.scalars(select(User).where(User.id == actor_id).with_for_update()
        .execution_options(populate_existing=True))).one_or_none()
    if not user or user.deleted or user.suspended:
        raise DeliveryError("account_unavailable", 404)
    stamp = digest([actor_id, title])
    group = await session.get(ChatGroup, group_id, populate_existing=True)
    if group:
        if group.creator_id != actor_id or group.creation_fingerprint != stamp:
            raise DeliveryError("group_request_conflict", 409)
        member_for(await members(session, group_id), actor_id)
        return await snapshot(session, group)
    # Bound metadata growth independently of message rate limits.
    from sqlalchemy import func
    count = await session.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == actor_id))
    if count >= 100:
        raise DeliveryError("group_limit_reached", 429)
    group = ChatGroup(id=group_id, creator_id=actor_id, creation_fingerprint=stamp,
        title=title, epoch=1, state="active", created_at=utc(now))
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group_id, user_id=actor_id, role="owner", joined_epoch=1, joined_at=utc(now)))
    await session.flush()
    return await snapshot(session, group)


def operation_value(action, expected_epoch, target_id=None, title=None, role=None, invite_id=None, *, control_stamp=None):
    value = [action, expected_epoch, target_id, title, role, invite_id]
    if control_stamp is not None:
        value.append(["atomic-control", control_stamp])
    return value


async def cancellation_fence(session, group_id, actor_id, request_id, stamp, device_id):
    cancellation = await session.get(GroupCancellation, (group_id, actor_id, request_id))
    if cancellation:
        if cancellation.fingerprint != stamp or cancellation.original_device_id != device_id:
            raise DeliveryError("group_request_conflict", 409)
        raise DeliveryError("group_operation_cancelled", 409)


async def operation(session, group, actor_id, request_id, value, expected_epoch, *, now, device_id=None):
    stamp = digest(value)
    await cancellation_fence(session, group.id, actor_id, request_id, stamp, device_id)
    old = await session.get(GroupOperation, (group.id, request_id))
    if old:
        if old.actor_id != actor_id or old.fingerprint != stamp:
            raise DeliveryError("group_request_conflict", 409)
        return False
    epoch_matches(group, expected_epoch)
    session.add(GroupOperation(group_id=group.id, request_id=request_id, actor_id=actor_id,
        fingerprint=stamp, created_at=utc(now),expected_epoch=expected_epoch,original_device_id=device_id))
    return True


async def mutate(session, *, group_id, actor_id, request_id, expected_epoch, action, now,
                 target_id=None, title=None, role=None, invite_id=None, control=None, device_id=None,
                 max_bytes=65536, max_pending=10000):
    # The control admission and membership authority must have the same commit.
    # Savepoint rollback also protects service callers that catch errors.
    async with session.begin_nested():
        return await _mutate(session, group_id=group_id, actor_id=actor_id, request_id=request_id,
            expected_epoch=expected_epoch, action=action, now=now, target_id=target_id,
            title=title, role=role, invite_id=invite_id, control=control, device_id=device_id,
            max_bytes=max_bytes, max_pending=max_pending)


async def _mutate(session, *, group_id, actor_id, request_id, expected_epoch, action, now,
                  target_id=None, title=None, role=None, invite_id=None, control=None, device_id=None,
                  max_bytes=65536, max_pending=10000):
    group, roster, users = await lock_group(session, group_id, actor_id, extra=[target_id] if target_id else [], allow_closed=action == "leave")
    if device_id is not None:
        device = await session.get(Device, device_id, populate_existing=True)
        if not device or not device.active or device.user_id != actor_id:
            raise DeliveryError("device_revoked", 401)
    value = [action, expected_epoch, target_id, title, role, invite_id]
    if control is not None:
        if action not in ("role", "remove", "leave") or control.kind != "control" or control.invited_user_id or not device_id:
            raise DeliveryError("invalid_atomic_group_control")
        value.append(["atomic-control", fanout_fingerprint(group_id, actor_id, device_id, control)])

    await cancellation_fence(session,group_id,actor_id,request_id,digest(value),device_id)
    previous = await session.get(GroupOperation, (group_id, request_id))
    if previous:
        if previous.actor_id != actor_id or previous.fingerprint != digest(value):
            raise DeliveryError("group_request_conflict", 409)
        if previous.admitted_result is None:
            # Pre-extension receipts have no immutable snapshot. A current
            # roster is not evidence of the original admitted outcome.
            raise DeliveryError("group_operation_outcome_unavailable", 409)
        return json.loads(previous.admitted_result)

    async def remember(result):
        record = await session.get(GroupOperation, (group_id, request_id))
        record.admitted_result = json.dumps(result,sort_keys=True,separators=(",",":")).encode()
        return result

    async def result_with_control(result):
        if control is None:
            return await remember(result)
        record = await session.get(GroupMessage, (group_id, control.id))
        if (not record or record.kind != "control" or record.sender_id != actor_id or
                record.sender_device_id != device_id or
                record.fingerprint != fanout_fingerprint(group_id, actor_id, device_id, control)):
            raise DeliveryError("group_request_conflict", 409)
        return await remember(result | {"control_acceptance": await message_result(session, group_id, record, now=now)})
    # Invitations are account capabilities; accepting/declining requires that
    # exact account, not existing group membership.
    invite = await session.get(GroupInvitation, invite_id) if invite_id else None
    consent = action in ("accept", "decline")
    if consent:
        if not invite or invite.group_id != group_id or invite.user_id != actor_id:
            raise DeliveryError("group_invitation_unavailable", 404)
    elif action == "leave":
        previous = await session.get(GroupOperation, (group_id, request_id))
        if previous:
            if previous.actor_id != actor_id or previous.fingerprint != digest(value):
                raise DeliveryError("group_request_conflict", 409)
            return await result_with_control({"left": True})
        if group.state != "active":
            raise DeliveryError("group_unavailable", 404)
        member_for(roster, actor_id)
    else:
        admin_for(roster, actor_id)
    # Include expected_epoch in idempotency identity: retries are exact bytes.
    if not await operation(session, group, actor_id, request_id, value, expected_epoch, now=now, device_id=device_id):
        if action == "leave":
            return await result_with_control({"left": True})
        if action == "decline":
            return await remember({"declined": True})
        member_for(await members(session, group_id), actor_id)
        return await result_with_control(await snapshot(session, group))
    if control is not None:
        if await session.get(GroupMessage, (group_id, control.id)):
            raise DeliveryError("group_control_already_admitted", 409)
        await send(session, group_id=group_id, actor_id=actor_id, device_id=device_id,
            fanout=control, now=now, max_bytes=max_bytes, max_pending=max_pending)
    if action in ("accept", "decline"):
        if invite.state != "pending" or utc(invite.expires_at) <= utc(now):
            raise DeliveryError("group_invitation_unavailable", 404)
        if action == "accept":
            if any(m.user_id == actor_id for m in roster):
                raise DeliveryError("group_already_member", 409)
            if len(roster) >= CAP:
                raise DeliveryError("group_full", 409)
            if await blocked_pair(session, [m.user_id for m in roster] + [actor_id], target=actor_id):
                raise DeliveryError("group_member_unavailable", 404)
            if any(u.deleted or u.suspended for u in users):
                raise DeliveryError("group_member_unavailable", 404)
            from sqlalchemy import func
            count = await session.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == actor_id))
            if count >= 100:
                raise DeliveryError("group_limit_reached", 429)
            session.add(GroupMember(group_id=group_id, user_id=actor_id, role="member",
                joined_epoch=group.epoch + 1, joined_at=utc(now)))
            invite.state = "accepted"
        else:
            invite.state = "declined"
    elif action == "invite":
        target = next((u for u in users if u.id == target_id), None)
        if not target or target.deleted or target.suspended:
            raise DeliveryError("group_member_unavailable", 404)
        if any(m.user_id == target_id for m in roster):
            raise DeliveryError("group_already_member", 409)
        if len(roster) >= CAP:
            raise DeliveryError("group_full", 409)
        if await blocked_pair(session, [m.user_id for m in roster] + [target_id], target=target_id):
            raise DeliveryError("group_member_unavailable", 404)
        pending = (await session.scalars(select(GroupInvitation).where(GroupInvitation.group_id == group_id,
            GroupInvitation.user_id == target_id, GroupInvitation.state == "pending"))).all()
        from sqlalchemy import func
        pending_count = await session.scalar(select(func.count()).select_from(GroupInvitation).where(
            GroupInvitation.group_id == group_id, GroupInvitation.state == "pending", GroupInvitation.expires_at > utc(now)))
        if pending_count - sum(utc(i.expires_at) > utc(now) for i in pending) >= CAP:
            raise DeliveryError("group_invitation_limit", 429)
        for old in pending:
            old.state = "cancelled"
        # The globally unique invitation ID cannot alias another operation.
        if await session.get(GroupInvitation, request_id):
            raise DeliveryError("group_request_conflict", 409)
        session.add(GroupInvitation(id=request_id, group_id=group_id, user_id=target_id,
            invited_by=actor_id, state="pending", created_at=utc(now), expires_at=utc(now) + timedelta(days=7)))
    elif action == "cancel-invite":
        if not invite or invite.group_id != group_id or invite.state != "pending":
            raise DeliveryError("group_invitation_unavailable", 404)
        invite.state = "cancelled"
    elif action == "rename":
        group.title = clean_title(title)
    elif action == "role":
        actor = member_for(roster, actor_id)
        target = member_for(roster, target_id)
        if actor.role != "owner" or actor_id == target_id or role not in ("admin", "member", "owner"):
            raise DeliveryError("group_permission_denied", 403)
        if role == "owner":
            actor.role = "admin"
        target.role = role
    elif action in ("remove", "leave"):
        target = member_for(roster, actor_id if action == "leave" else target_id)
        if action == "remove":
            actor = member_for(roster, actor_id)
            if target.user_id == actor_id or target.role == "owner" or (actor.role == "admin" and target.role != "member"):
                raise DeliveryError("group_permission_denied", 403)
        await depart(session, group, roster, target, now=now, increment=False)
    else:
        raise ValueError("unknown_group_action")
    group.epoch += 1
    await session.flush()
    await notify_group(session, group_id, now=now, extra=[actor_id] + ([target_id] if target_id else []))
    if action == "leave":
        return await result_with_control({"left": True})
    if action == "decline":
        return await remember({"declined": True})
    return await result_with_control(await snapshot(session, group))


async def depart(session, group, roster, target, *, now, increment=True):
    remaining = [m for m in roster if m.user_id != target.user_id]
    if target.role == "owner" and remaining:
        successor = sorted(remaining, key=lambda m: (m.role != "admin", utc(m.joined_at), m.user_id))[0]
        successor.role = "owner"
    await session.delete(target)
    if not remaining:
        group.state = "closed"
        await session.execute(update(GroupInvitation).where(GroupInvitation.group_id == group.id,
            GroupInvitation.state == "pending").values(state="cancelled"))
    await session.execute(update(PendingMessage).where(PendingMessage.group_id == group.id,
        PendingMessage.recipient_id == target.user_id, PendingMessage.state == "accepted")
        .values(state="unavailable", ciphertext=None))
    if increment:
        group.epoch += 1
    await session.flush()


async def revoke_memberships(session, user_id, *, now, shared_with=None, deleting=False):
    """Caller holds user lock (and peer lock for block), before group locks."""
    membership_ids = set((await session.scalars(select(GroupMember.group_id).where(
        GroupMember.user_id == user_id))).all())
    invitation_filter = or_(GroupInvitation.user_id == user_id, GroupInvitation.invited_by == user_id)
    if shared_with:
        invitation_filter = and_(invitation_filter, or_(GroupInvitation.user_id == shared_with,
            GroupInvitation.invited_by == shared_with))
    invitations = select(GroupInvitation).where(invitation_filter)
    if not deleting:
        invitations = invitations.where(GroupInvitation.state == "pending")
    candidates = (await session.scalars(invitations)).all()
    affected = membership_ids | {i.group_id for i in candidates}
    if deleting:
        affected |= set((await session.scalars(select(ChatGroup.id).where(ChatGroup.creator_id == user_id))).all())
    # Include invitation-only groups in the same globally ordered lock set.
    # Otherwise two deletions with crossed historical invitations could take
    # member groups in one order and invitation groups in the opposite order.
    locked = (await session.scalars(select(ChatGroup).where(ChatGroup.id.in_(affected))
        .order_by(ChatGroup.id).with_for_update().execution_options(populate_existing=True))).all()
    notify_ids = {i.user_id for i in candidates} - {user_id}
    invitation_groups = {i.group_id for i in candidates}
    for group in locked:
        if group.id in invitation_groups:
            notify_ids |= {m.user_id for m in await members(session, group.id)} - {user_id}
        if group.id not in membership_ids:
            continue
        roster = await members(session, group.id)
        if shared_with and not any(m.user_id == shared_with for m in roster):
            continue
        target = next((m for m in roster if m.user_id == user_id), None)
        if target:
            await depart(session, group, roster, target, now=now)
            notify_ids |= {m.user_id for m in roster if m.user_id != user_id}
    await notify_users(session, notify_ids, now=now)
    # Refresh under group locks before writing, including rows authored by this
    # account in a group it has already left.
    candidates = (await session.scalars(invitations.execution_options(populate_existing=True))).all()
    for invite in candidates:
        if invite.state == "pending":
            invite.state = "cancelled"
    if deleting:
        await session.execute(delete(GroupInvitation).where(invitation_filter))
        await session.execute(delete(GroupOperation).where(GroupOperation.actor_id == user_id))
        await session.execute(delete(GroupCancellation).where(GroupCancellation.actor_id == user_id))
        await session.execute(delete(GroupMessage).where(GroupMessage.sender_id == user_id))
        await session.execute(update(ChatGroup).where(ChatGroup.creator_id == user_id).values(creator_id=None))


@dataclass(frozen=True)
class Fanout:
    id: str
    epoch: int
    created_at: object
    envelopes: tuple[Envelope, ...]
    kind: str = "message"
    invited_user_id: str | None = None


async def cancel_operation(session, *, group_id, actor_id, request_id, action, expected_epoch,
                           original_device_id, device_id, now, target_id=None, title=None,
                           role=None, invite_id=None, control=None):
    """Resolve one exact operation under admission's user/group locks.

    Tombstones are actor-namespaced: one member cannot reserve another member's
    request ID. Transport errors retain the client's original immutable journal.
    """
    async with session.begin_nested():
        group, roster, _ = await lock_group(session,group_id,actor_id,
            extra=[target_id] if target_id else [],allow_closed=True)
        current_device = await session.get(Device,device_id,populate_existing=True)
        original_device = await session.get(Device,original_device_id,populate_existing=True)
        if not current_device or not current_device.active or current_device.user_id != actor_id:
            raise DeliveryError("device_revoked",401)
        # A revoked original device may still have an uncertain prepared request;
        # a new authenticated device can reconcile it without remapping its ID.
        if not original_device or original_device.user_id != actor_id:
            raise DeliveryError("group_request_conflict",409)
        actions = {"rename","invite","accept","decline","cancel-invite","role","remove","leave","control"}
        if action not in actions or type(expected_epoch) is not int or expected_epoch < 1:
            raise DeliveryError("invalid_group_operation_descriptor")
        fields = {"target_id":target_id,"title":title,"role":role,"invite_id":invite_id}
        needed = {"rename":{"title"},"invite":{"target_id"},"accept":{"invite_id"},
            "decline":{"invite_id"},"cancel-invite":{"invite_id"},"role":{"target_id","role"},
            "remove":{"target_id"},"leave":set(),"control":set()}[action]
        if {key for key,value in fields.items() if value is not None} != needed:
            raise DeliveryError("invalid_group_operation_descriptor")
        if action == "rename": clean_title(title)
        if action == "role" and role not in ("owner","admin","member"):
            raise DeliveryError("invalid_group_operation_descriptor")
        if control is not None and (control.kind != "control" or
            (action != "control" and (action not in ("role","remove","leave") or control.invited_user_id))):
            raise DeliveryError("invalid_group_operation_descriptor")
        if action == "control" and (control is None or control.id != request_id or control.epoch != expected_epoch):
            raise DeliveryError("invalid_group_operation_descriptor")
        stamp = digest(operation_value(action,expected_epoch,target_id,title,role,invite_id,
            control_stamp=fanout_fingerprint(group_id,actor_id,original_device_id,control) if control else None))
        old = await session.get(GroupOperation,(group_id,request_id))
        if old:
            if old.actor_id != actor_id or old.fingerprint != stamp:
                raise DeliveryError("group_request_conflict",409)
            if old.admitted_result is None or old.original_device_id is None:
                raise DeliveryError("group_operation_outcome_unavailable",409)
            if old.original_device_id != original_device_id:
                raise DeliveryError("group_request_conflict",409)
            return {"status":"admitted","request_id":request_id,"group_id":group_id,
                "result":json.loads(old.admitted_result)}
        if action == "control":
            record = await session.get(GroupMessage,(group_id,request_id))
            if record:
                if (record.kind != "control" or record.sender_id != actor_id or
                    record.sender_device_id != original_device_id or
                    record.fingerprint != fanout_fingerprint(group_id,actor_id,original_device_id,control)):
                    raise DeliveryError("group_request_conflict",409)
                if record.admitted_result is None:
                    raise DeliveryError("group_operation_outcome_unavailable",409)
                return {"status":"admitted","request_id":request_id,"group_id":group_id,
                    "result":json.loads(record.admitted_result)}
        tombstone = await session.get(GroupCancellation,(group_id,actor_id,request_id))
        if tombstone:
            if tombstone.fingerprint != stamp or tombstone.original_device_id != original_device_id:
                raise DeliveryError("group_request_conflict",409)
        else:
            # Authorize against current authority for an unadmitted operation.
            # Existing exact outcomes above need no new membership or roster.
            if action in ("accept","decline"):
                invite = await session.get(GroupInvitation,invite_id)
                if not invite or invite.group_id != group_id or invite.user_id != actor_id:
                    raise DeliveryError("group_invitation_unavailable",404)
            elif group.state == "closed" and group.creator_id == actor_id:
                pass  # A closed creator's late mutation can never be admitted.
            elif action in ("leave","control"):
                member_for(roster,actor_id)
            else:
                member = admin_for(roster,actor_id)
                if action == "role" and member.role != "owner":
                    raise DeliveryError("group_permission_denied",403)
            # Only monotonic admission fences permit cleanup. A current/future
            # expected epoch is never forgotten merely because days passed.
            stale = [GroupCancellation.expected_epoch < group.epoch,
                GroupCancellation.control_expires_at <= utc(now)]
            if group.state != "active": stale.append(GroupCancellation.group_id == group_id)
            await session.execute(delete(GroupCancellation).where(GroupCancellation.group_id == group_id,or_(*stale)))
            from sqlalchemy import func
            count = await session.scalar(select(func.count()).select_from(GroupCancellation).where(
                GroupCancellation.group_id == group_id,GroupCancellation.actor_id == actor_id))
            if count >= 256:
                raise DeliveryError("group_cancellation_limit",429)
            session.add(GroupCancellation(group_id=group_id,actor_id=actor_id,request_id=request_id,
                fingerprint=stamp,expected_epoch=expected_epoch,original_device_id=original_device_id,
                control_expires_at=utc(control.created_at)+timedelta(hours=72) if control else None,
                created_at=utc(now)))
            await session.flush()
        return {"status":"cancelled","request_id":request_id,"group_id":group_id,"expected_epoch":expected_epoch}


async def message_result(session, group_id, record, *, now):
    found = []
    for message_id in json.loads(record.envelope_ids):
        item = await session.get(PendingMessage, message_id)
        state = item.state if item else "expired"
        if item and state == "accepted" and utc(item.expires_at) <= utc(now):
            item.state, item.ciphertext, state = "expired", None, "expired"
        found.append({"id": message_id, "state": state, "expires_at": utc(record.expires_at).isoformat()})
    return {"id": record.id, "group_id": group_id, "epoch": record.epoch, "admitted": True, "deliveries": found}


def fanout_fingerprint(group_id, actor_id, device_id, fanout):
    stamp = digest([group_id, fanout.id, actor_id, device_id, fanout.epoch, utc(fanout.created_at).isoformat(),
        sorted(fingerprint(e) for e in fanout.envelopes)])
    return digest([stamp, fanout.kind, fanout.invited_user_id])


async def send(session, *, group_id, actor_id, device_id, fanout, now, max_bytes=65536, max_pending=10000):
    group, roster, users = await lock_group(session, group_id, actor_id,
        extra=[fanout.invited_user_id] if fanout.invited_user_id else [])
    member_for(roster, actor_id)
    device = await session.get(Device, device_id, populate_existing=True)
    if not device or not device.active or device.user_id != actor_id:
        raise DeliveryError("device_revoked", 401)
    sent, now = utc(fanout.created_at), utc(now)
    if fanout.kind not in ("message", "control"):
        raise DeliveryError("invalid_group_envelope")
    stamp = fanout_fingerprint(group_id, actor_id, device_id, fanout)
    old = await session.get(GroupMessage, (group_id, fanout.id))
    if old:
        if old.sender_id != actor_id or old.sender_device_id != device_id or old.fingerprint != stamp:
            raise DeliveryError("group_request_conflict", 409)
        return await message_result(session, group_id, old, now=now)
    if fanout.kind == "control":
        cancellation_stamp = digest(operation_value("control",fanout.epoch,control_stamp=stamp))
        await cancellation_fence(session,group_id,actor_id,fanout.id,cancellation_stamp,device_id)
    epoch_matches(group, fanout.epoch)
    if sent > now + timedelta(minutes=5):
        raise DeliveryError("clock_ahead")
    if sent + timedelta(hours=72) <= now:
        raise DeliveryError("message_expired", 410)
    if any(u.deleted or u.suspended for u in users):
        raise DeliveryError("group_member_unavailable", 404)
    if await blocked_pair(session, [m.user_id for m in roster]):
        raise DeliveryError("group_member_unavailable", 404)
    devices = (await session.scalars(select(Device).where(Device.user_id.in_([m.user_id for m in roster]),
        Device.active.is_(True)))).all()
    routes = {(d.user_id, d.id) for d in devices if d.user_id != actor_id}
    if fanout.invited_user_id:
        if fanout.kind != "control":
            raise DeliveryError("invalid_group_envelope")
        admin_for(roster, actor_id)
        invite = await session.scalar(select(GroupInvitation.id).where(GroupInvitation.group_id == group_id,
            GroupInvitation.user_id == fanout.invited_user_id, GroupInvitation.state == "pending",
            GroupInvitation.expires_at > now).limit(1))
        if not invite:
            raise DeliveryError("group_invitation_unavailable", 404)
        if await blocked_pair(session, [m.user_id for m in roster] + [fanout.invited_user_id], target=fanout.invited_user_id):
            raise DeliveryError("group_member_unavailable", 404)
        invited_devices = (await session.scalars(select(Device).where(Device.user_id == fanout.invited_user_id,
            Device.active.is_(True)))).all()
        if len(invited_devices) != 1:
            raise DeliveryError("group_device_state_invalid", 409)
        routes.add((fanout.invited_user_id, invited_devices[0].id))
    if len(devices) != len(roster) or len({d.user_id for d in devices}) != len(roster):
        raise DeliveryError("group_device_state_invalid", 409)
    supplied = {(e.recipient_id, e.recipient_device_id) for e in fanout.envelopes}
    if routes != supplied or len(supplied) != len(fanout.envelopes):
        raise DeliveryError("group_recipients_changed", 409)
    ids = [e.id for e in fanout.envelopes]
    if len(set(ids)) != len(ids):
        raise DeliveryError("group_request_conflict", 409)
    for e in fanout.envelopes:
        if e.sender_id != actor_id or e.sender_device_id != device_id or utc(e.created_at) != sent:
            raise DeliveryError("invalid_group_envelope")
    # A savepoint also preserves all-or-nothing semantics for service callers
    # that catch a DeliveryError inside their outer transaction.
    async with session.begin_nested():
        if ids and await session.scalar(select(PendingMessage.id).where(PendingMessage.id.in_(ids)).limit(1)):
            raise DeliveryError("message_id_conflict", 409)
        for envelope in sorted(fanout.envelopes, key=lambda e: e.recipient_device_id):
            item = await accept(session, envelope, now=now, max_bytes=max_bytes, max_pending=max_pending)
            item.group_id, item.group_epoch, item.group_message_id = group_id, group.epoch, fanout.id
            item.group_kind = fanout.kind
            from .push import enqueue
            await enqueue(session, item.recipient_device_id, now, item.expires_at)
        record = GroupMessage(group_id=group_id, id=fanout.id, sender_id=actor_id, sender_device_id=device_id,
            kind=fanout.kind, epoch=group.epoch, fingerprint=stamp, envelope_ids=json.dumps(ids).encode(),
            expires_at=min(sent, now) + timedelta(hours=72))
        session.add(record)
        await session.flush()
    result = await message_result(session, group_id, record, now=now)
    record.admitted_result = json.dumps(result,sort_keys=True,separators=(",",":")).encode()
    return result


async def expire(session, *, now):
    obsolete = select(ChatGroup.id).where(ChatGroup.id == GroupCancellation.group_id,
        or_(ChatGroup.state != "active",ChatGroup.epoch > GroupCancellation.expected_epoch)).exists()
    await session.execute(delete(GroupCancellation).where(or_(obsolete,
        GroupCancellation.control_expires_at <= utc(now))))
    await session.execute(delete(GroupMessage).where(or_(
        and_(GroupMessage.kind == "message", GroupMessage.expires_at < utc(now) - timedelta(days=7)),
        and_(GroupMessage.kind == "control", GroupMessage.expires_at < utc(now) - timedelta(days=27)))))
    await session.execute(delete(GroupOperation).where(GroupOperation.created_at < utc(now) - timedelta(days=30)))
    await session.execute(update(GroupInvitation).where(GroupInvitation.state == "pending",
        GroupInvitation.expires_at <= utc(now)).values(state="expired"))
