"""Opaque-byte relay/lifecycle tests; these do not qualify Signal encryption."""
from dataclasses import replace
from datetime import timedelta
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from conftest import NOW
from vipi import groups
from vipi.accounts import register_device, set_block
from vipi.db import ChatGroup, GroupMember, GroupMessage, GroupOperation, PendingMessage, User
from vipi.deletion import request_deletion
from vipi.delivery import DeliveryError, Envelope, accept, acknowledge, expire
from vipi.reports import restrict, submit


def uid():
    return str(uuid4())


async def current(db, gid):
    async with db.sessions() as s:
        return await groups.snapshot(s, await s.get(ChatGroup, gid))


async def create(db):
    gid = uid()
    async with db.sessions.begin() as s:
        await groups.create(s,actor_id="alice",group_id=gid,title="Friends",now=NOW)
    return gid


async def change(db,gid,action,actor="alice",epoch=None,request_id=None,**extra):
    if epoch is None:
        epoch = (await current(db,gid))["epoch"]
    async with db.sessions.begin() as s:
        return await groups.mutate(s,group_id=gid,actor_id=actor,action=action,expected_epoch=epoch,
            request_id=request_id or uid(),now=NOW,**extra)


async def join(db,gid,who):
    invite = uid()
    await change(db,gid,"invite",target_id=who,request_id=invite)
    return await change(db,gid,"accept",actor=who,invite_id=invite)


def fanout(group, recipients=("bob","eve")):
    return groups.Fanout(uid(),group["epoch"],NOW,tuple(Envelope(uid(),"alice","alice-phone",who,who+"-phone",
        NOW,b"opaque fixture is not encryption"*2,3) for who in recipients))


async def send(db,gid,body,**extra):
    async with db.sessions.begin() as s:
        return await groups.send(s,group_id=gid,actor_id="alice",device_id="alice-phone",fanout=body,now=NOW,**extra)


async def test_explicit_consent_and_create_retry(db):
    gid = await create(db)
    async with db.sessions.begin() as s:
        retry = await groups.create(s,actor_id="alice",group_id=gid,title="Friends",now=NOW)
        assert retry["epoch"] == 1 and len(retry["members"]) == 1
        with pytest.raises(DeliveryError,match="group_unavailable"):
            groups.member_for(await groups.members(s,gid),"eve")
    with pytest.raises(DeliveryError,match="group_request_conflict"):
        async with db.sessions.begin() as s:
            await groups.create(s,actor_id="alice",group_id=gid,title="Changed",now=NOW)
    invite = uid()
    await change(db,gid,"invite",target_id="bob",request_id=invite)
    assert len((await current(db,gid))["members"]) == 1
    async with db.sessions() as s:
        inbox = await groups.list_groups(s,"bob",now=NOW)
        assert inbox["groups"] == [] and inbox["invitations"][0]["id"] == invite
    with pytest.raises(DeliveryError,match="group_invitation_unavailable"):
        await change(db,gid,"accept",actor="eve",invite_id=invite)
    result = await change(db,gid,"accept",actor="bob",invite_id=invite)
    assert [m["user_id"] for m in result["members"]] == ["alice","bob"]
    assert result["members"][1]["joined_epoch"] == result["epoch"]


async def test_epoch_idempotency_permissions_and_transfer(db):
    gid = await create(db)
    await join(db,gid,"bob")
    await join(db,gid,"eve")
    snap,req = await current(db,gid),uid()
    result = await change(db,gid,"rename",title="Family",request_id=req,epoch=snap["epoch"])
    assert await change(db,gid,"rename",title="Family",request_id=req,epoch=snap["epoch"]) == result
    with pytest.raises(DeliveryError,match="group_request_conflict"):
        await change(db,gid,"rename",title="Different",request_id=req,epoch=snap["epoch"])
    with pytest.raises(DeliveryError,match="group_epoch_changed"):
        await change(db,gid,"rename",title="Stale",epoch=snap["epoch"])
    with pytest.raises(DeliveryError,match="group_permission_denied"):
        await change(db,gid,"rename",actor="bob",title="No")
    await change(db,gid,"role",target_id="bob",role="admin")
    await change(db,gid,"rename",actor="bob",title="Allowed")
    with pytest.raises(DeliveryError,match="group_permission_denied"):
        await change(db,gid,"remove",actor="bob",target_id="alice")
    await change(db,gid,"role",target_id="eve",role="owner")
    assert {m["user_id"]:m["role"] for m in (await current(db,gid))["members"]} == {"alice":"admin","bob":"admin","eve":"owner"}
    await change(db,gid,"leave",actor="eve")
    assert next(m for m in (await current(db,gid))["members"] if m["user_id"] == "alice")["role"] == "owner"


async def test_final_leave_closes_and_retries(db):
    gid,req = await create(db),uid()
    assert await change(db,gid,"leave",epoch=1,request_id=req) == {"left":True}
    assert await change(db,gid,"leave",epoch=1,request_id=req) == {"left":True}
    assert (await current(db,gid))["state"] == "closed"
    with pytest.raises(DeliveryError,match="group_unavailable"):
        await send(db,gid,fanout({"epoch":2},()))


async def test_exact_fanout_idempotency_and_receipts(db):
    gid = await create(db)
    await join(db,gid,"bob")
    await join(db,gid,"eve")
    body = fanout(await current(db,gid))
    for broken in (replace(body,envelopes=body.envelopes[:1]),replace(body,envelopes=(body.envelopes[0],body.envelopes[0]))):
        with pytest.raises(DeliveryError,match="group_recipients_changed"):
            await send(db,gid,broken)
    first = await send(db,gid,body)
    assert all(e["state"] == "accepted" for e in first["deliveries"])
    assert await send(db,gid,body) == first
    changed = replace(body,envelopes=(replace(body.envelopes[0],ciphertext=b"changed"*12),body.envelopes[1]))
    with pytest.raises(DeliveryError,match="group_request_conflict"):
        await send(db,gid,changed)
    async with db.sessions.begin() as s:
        await acknowledge(s,body.envelopes[0].id,"bob","bob-phone",now=NOW)
    assert (await send(db,gid,body))["deliveries"][0]["state"] == "delivered"
    async with db.sessions() as s:
        items = (await s.scalars(select(PendingMessage))).all()
        assert len(items) == 2
        assert {(p.group_id,p.group_epoch,p.group_message_id) for p in items} == {(gid,body.epoch,body.id)}


async def test_queue_failure_atomic_even_if_caller_catches(db):
    gid = await create(db)
    await join(db,gid,"bob")
    await join(db,gid,"eve")
    async with db.sessions.begin() as s:
        await accept(s,Envelope(uid(),"bob","bob-phone","eve","eve-phone",NOW,b"x"*64),now=NOW)
    body = fanout(await current(db,gid))
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError,match="recipient_queue_full"):
            await groups.send(s,group_id=gid,actor_id="alice",device_id="alice-phone",fanout=body,now=NOW,max_pending=1)
    async with db.sessions() as s:
        assert await s.get(PendingMessage,body.envelopes[0].id) is None
        assert await s.get(GroupMessage,(gid,body.id)) is None
        assert await s.scalar(select(func.count()).select_from(PendingMessage)) == 1


async def test_no_join_backfill_departure_purge_and_stale_resend(db):
    gid = await create(db)
    await join(db,gid,"bob")
    first = fanout(await current(db,gid),("bob",))
    await send(db,gid,first)
    await join(db,gid,"eve")
    async with db.sessions() as s:
        assert not (await s.scalars(select(PendingMessage).where(PendingMessage.recipient_id == "eve"))).all()
    await change(db,gid,"remove",target_id="bob")
    async with db.sessions() as s:
        item = await s.get(PendingMessage,first.envelopes[0].id)
        assert item.state == "unavailable" and item.ciphertext is None
    assert (await send(db,gid,first))["deliveries"][0]["state"] == "unavailable"
    with pytest.raises(DeliveryError,match="group_epoch_changed"):
        await send(db,gid,replace(first,id=uid()))
    with pytest.raises(DeliveryError,match="group_unavailable"):
        await change(db,gid,"rename",actor="bob",title="No")
    await send(db,gid,fanout(await current(db,gid),("eve",)))


async def test_block_leaves_shared_groups_and_cancels_pending_invites(db):
    gid = await create(db)
    await join(db,gid,"bob")
    await send(db,gid,fanout(await current(db,gid),("bob",)))
    async with db.sessions.begin() as s:
        await set_block(s,blocker_id="bob",blocked_id="alice",blocked=True,now=NOW)
    assert [m["user_id"] for m in (await current(db,gid))["members"]] == ["alice"]
    async with db.sessions.begin() as s:
        await set_block(s,blocker_id="bob",blocked_id="alice",blocked=False,now=NOW)
    assert len((await current(db,gid))["members"]) == 1
    invite = uid()
    await change(db,gid,"invite",target_id="bob",request_id=invite)
    async with db.sessions.begin() as s:
        await set_block(s,blocker_id="bob",blocked_id="alice",blocked=True,now=NOW)
    with pytest.raises(DeliveryError,match="group_invitation_unavailable"):
        await change(db,gid,"accept",actor="bob",invite_id=invite)


async def test_blocked_member_prevents_invite_even_if_inviter_unblocked(db):
    gid = await create(db)
    await join(db,gid,"bob")
    async with db.sessions.begin() as s:
        await set_block(s,blocker_id="bob",blocked_id="eve",blocked=True,now=NOW)
    with pytest.raises(DeliveryError,match="group_member_unavailable"):
        await change(db,gid,"invite",target_id="eve")


async def test_invite_decline_cancel_expiry_and_retry(db):
    gid = await create(db)
    invite,req = uid(),uid()
    await change(db,gid,"invite",target_id="bob",request_id=invite)
    epoch = (await current(db,gid))["epoch"]
    assert await change(db,gid,"decline",actor="bob",invite_id=invite,request_id=req,epoch=epoch) == {"declined":True}
    assert await change(db,gid,"decline",actor="bob",invite_id=invite,request_id=req,epoch=epoch) == {"declined":True}
    invite = uid()
    await change(db,gid,"invite",target_id="bob",request_id=invite)
    await change(db,gid,"cancel-invite",invite_id=invite)
    with pytest.raises(DeliveryError,match="group_invitation_unavailable"):
        await change(db,gid,"accept",actor="bob",invite_id=invite)
    invite = uid()
    await change(db,gid,"invite",target_id="eve",request_id=invite)
    async with db.sessions.begin() as s:
        await groups.expire(s,now=NOW+timedelta(days=8))
        assert (await groups.list_groups(s,"eve",now=NOW+timedelta(days=8)))["invitations"] == []
    with pytest.raises(DeliveryError,match="group_invitation_unavailable"):
        await change(db,gid,"accept",actor="eve",invite_id=invite)


async def test_cap_accept_rechecks_seat(db):
    gid = await create(db)
    invite = uid()
    await change(db,gid,"invite",target_id="bob",request_id=invite)
    async with db.sessions.begin() as s:
        for n in range(15):
            who = "member"+str(n)
            s.add(User(id=who,subject=who,username=who,display_name=who,created_at=NOW))
        await s.flush()
        for n in range(15):
            s.add(GroupMember(group_id=gid,user_id="member"+str(n),role="member",joined_epoch=2,joined_at=NOW))
    with pytest.raises(DeliveryError,match="group_full"):
        await change(db,gid,"accept",actor="bob",invite_id=invite)
    assert len((await current(db,gid))["members"]) == 16


async def test_identity_replacement_no_redirect_and_sender_revocation(db):
    gid = await create(db)
    await join(db,gid,"bob")
    body = fanout(await current(db,gid),("bob",))
    await send(db,gid,body)
    async with db.sessions.begin() as s:
        await register_device(s,user_id="bob",device_id="bob-new",secret=secrets.token_urlsafe(32),replace_active=True,
            service_secret="x"*43,now=NOW)
    assert (await send(db,gid,body))["deliveries"][0]["state"] == "identity_changed"
    with pytest.raises(DeliveryError,match="group_recipients_changed"):
        await send(db,gid,replace(body,id=uid()))
    async with db.sessions.begin() as s:
        await register_device(s,user_id="alice",device_id="alice-new",secret=secrets.token_urlsafe(32),replace_active=True,
            service_secret="x"*43,now=NOW)
    with pytest.raises(DeliveryError,match="device_revoked"):
        await send(db,gid,body)


async def test_expiry_cannot_resurrect_after_retry_metadata_purge(db):
    gid = await create(db)
    await join(db,gid,"bob")
    body = fanout(await current(db,gid),("bob",))
    await send(db,gid,body)
    async with db.sessions.begin() as s:
        await expire(s,now=NOW+timedelta(days=11))
        await groups.expire(s,now=NOW+timedelta(days=11))
    with pytest.raises(DeliveryError,match="message_expired"):
        async with db.sessions.begin() as s:
            await groups.send(s,group_id=gid,actor_id="alice",device_id="alice-phone",fanout=body,now=NOW+timedelta(days=11))


async def test_deletion_suspension_revoke_groups_preserve_peers(db):
    gid = await create(db)
    await join(db,gid,"bob")
    await join(db,gid,"eve")
    await send(db,gid,fanout(await current(db,gid)))
    async with db.sessions.begin() as s:
        await request_deletion(s,subject="user_alice",account_id="alice",receipt_secret=secrets.token_urlsafe(32),
            service_secret="x"*43,now=NOW)
    async with db.sessions() as s:
        assert await s.get(User,"alice") is None
        assert await s.scalar(select(func.count()).select_from(GroupOperation).where(GroupOperation.actor_id == "alice")) == 0
        assert await s.scalar(select(func.count()).select_from(GroupMessage).where(GroupMessage.sender_id == "alice")) == 0
        assert (await s.get(ChatGroup,gid)).creator_id is None
    snap = await current(db,gid)
    assert {m["user_id"] for m in snap["members"]} == {"bob","eve"}
    owner = next(m["user_id"] for m in snap["members"] if m["role"] == "owner")
    async with db.sessions.begin() as s:
        await restrict(s,user_id=owner,suspended=True,operator="qa",reason="spam",now=NOW)
    assert len((await current(db,gid))["members"]) == 1


async def test_report_uses_individual_envelope_with_consent(db):
    gid = await create(db)
    await join(db,gid,"bob")
    body = fanout(await current(db,gid),("bob",))
    await send(db,gid,body)
    async with db.sessions.begin() as s:
        result = await submit(s,user_id="bob",report_id=uid(),reported_user_id="alice",message_id=body.envelopes[0].id,
            reason="harassment",selected_text="selected original",consent_version="report-v1",secret="x"*43,now=NOW)
        assert result["reported"] is True
    with pytest.raises(DeliveryError,match="invalid_report"):
        async with db.sessions.begin() as s:
            await submit(s,user_id="eve",report_id=uid(),reported_user_id="alice",message_id=body.envelopes[0].id,
                reason="harassment",selected_text="forged",consent_version="report-v1",secret="x"*43,now=NOW)


async def test_authenticated_control_transport_current_members_and_pending_invitee(db):
    gid = await create(db)
    await join(db,gid,"bob")
    invite = uid()
    await change(db,gid,"invite",target_id="eve",request_id=invite)
    body = replace(fanout(await current(db,gid)),kind="control",invited_user_id="eve")
    result = await send(db,gid,body)
    assert len(result["deliveries"]) == 2
    async with db.sessions() as s:
        pending = (await s.scalars(select(PendingMessage).where(PendingMessage.group_id == gid))).all()
        assert len(pending) == 2 and all(p.group_kind == "control" for p in pending)
    assert await send(db,gid,body) == result
    with pytest.raises(DeliveryError,match="group_request_conflict"):
        await send(db,gid,replace(body,kind="message",invited_user_id=None))
    await change(db,gid,"cancel-invite",invite_id=invite)
    with pytest.raises(DeliveryError,match="group_invitation_unavailable"):
        await send(db,gid,replace(body,id=uid(),epoch=(await current(db,gid))["epoch"]))


async def test_invitation_wakeup_survives_push_without_pending_chat(db):
    from test_push import Provider
    from vipi.push import process_pushes,register
    gid = await create(db)
    async with db.sessions.begin() as s:
        await register(s,user_id="bob",device_id="bob-phone",provider="fcm",environment="production",
            token="opaque-registration-token",secret="a"*43,now=NOW)
    await change(db,gid,"invite",target_id="bob")
    provider = Provider()
    result = await process_pushes(db,provider,secret="a"*43,now=NOW)
    assert result["sent"] == 1 and provider.calls == [("bob-phone","opaque-registration-token")]
