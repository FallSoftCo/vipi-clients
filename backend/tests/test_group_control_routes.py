"""Opaque CONTROL repair routing; DATA never drops an unavailable member.

Actual Signal and cross-platform evidence is recorded separately. Raw legacy
block/suspension fixtures retain the roster deliberately to exercise repair.
"""
from dataclasses import replace

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_groups import create, current, fanout, join, send, uid, change
from test_groups_atomic import atomic
from vipi import groups
from vipi.db import Block, ChatGroup, Device, GroupMember, GroupMessage, PendingMessage, User
from vipi.delivery import DeliveryError


async def three(db):
    gid = await create(db)
    await join(db, gid, "bob")
    await join(db, gid, "eve")
    return gid


async def actor_snapshot(db, gid, actor):
    async with db.sessions() as s:
        return await groups.snapshot(s, await s.get(ChatGroup, gid), actor_id=actor)


def route_map(snapshot):
    return {m["user_id"]: m["device_id"] for m in snapshot["members"]}


async def test_missing_device_can_be_removed_with_only_current_eligible_control(db):
    gid = await three(db)
    async with db.sessions.begin() as s:
        (await s.get(Device, "bob-phone")).active = False
    snapshot = await actor_snapshot(db, gid, "alice")
    assert route_map(snapshot) == {"alice": "alice-phone", "bob": None, "eve": "eve-phone"}
    with pytest.raises(DeliveryError, match="group_device_state_invalid"):
        await send(db, gid, fanout(snapshot, ("eve",)))
    body = replace(fanout(snapshot, ("eve",)), kind="control")
    result = await atomic(db, gid, "remove", body, target_id="bob")
    assert {m["user_id"] for m in result["members"]} == {"alice", "eve"}
    assert result["control_acceptance"]["admitted"] is True
    async with db.sessions() as s:
        assert await s.get(GroupMember, (gid, "bob")) is None
        assert [p.recipient_id for p in (await s.scalars(select(PendingMessage))).all()] == ["eve"]


@pytest.mark.parametrize("state", ["suspended", "deleted"])
async def test_restricted_legacy_member_is_control_ineligible_but_data_stays_strict(db, state):
    gid = await three(db)
    async with db.sessions.begin() as s:
        setattr(await s.get(User, "bob"), state, True)
    snapshot = await actor_snapshot(db, gid, "alice")
    assert route_map(snapshot)["bob"] is None
    with pytest.raises(DeliveryError, match="group_member_unavailable"):
        await send(db, gid, fanout(snapshot, ("eve",)))
    accepted = await send(db, gid, replace(fanout(snapshot, ("eve",)), kind="control"))
    assert accepted["admitted"] is True and len(accepted["deliveries"]) == 1


async def test_control_block_filter_is_actor_relative_and_data_blocks_any_pair(db):
    gid = await three(db)
    async with db.sessions.begin() as s:
        s.add(Block(blocker_id="alice", blocked_id="bob"))
    alice = await actor_snapshot(db, gid, "alice")
    eve = await actor_snapshot(db, gid, "eve")
    assert route_map(alice)["bob"] is None
    assert route_map(eve)["bob"] == "bob-phone"
    with pytest.raises(DeliveryError, match="group_member_unavailable"):
        await send(db, gid, fanout(alice, ("eve",)))
    admitted = await send(db, gid, replace(fanout(alice, ("eve",)), kind="control"))
    assert admitted["admitted"] is True
    supplied_blocked = replace(fanout(alice), kind="control")
    with pytest.raises(DeliveryError, match="group_recipients_changed"):
        await send(db, gid, supplied_blocked)


async def test_multiple_active_identities_fail_closed_even_for_ineligible_member(db):
    gid = await three(db)
    async with db.sessions.begin() as s:
        (await s.get(User, "bob")).suspended = True
        s.add(Device(id="bob-corrupt-second", user_id="bob", credential_hash="z" * 64, active=True, created_at=NOW))
    with pytest.raises(DeliveryError, match="group_device_state_invalid"):
        await actor_snapshot(db, gid, "alice")
    # Use an earlier cached shape; recipient corruption still fails under locks.
    body = groups.Fanout(uid(), 5, NOW, (), "control")
    with pytest.raises(DeliveryError, match="group_device_state_invalid"):
        await send(db, gid, body)


async def test_control_cannot_omit_eligible_or_include_ineligible_route(db):
    gid = await three(db)
    async with db.sessions.begin() as s:
        (await s.get(Device, "bob-phone")).active = False
    snapshot = await current(db, gid)
    for recipients in ((), ("bob", "eve")):
        body = replace(fanout(snapshot, recipients), kind="control")
        with pytest.raises(DeliveryError, match="group_recipients_changed"):
            await atomic(db, gid, "remove", body, target_id="bob")
    async with db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(GroupMessage)) == 0
        assert await s.scalar(select(func.count()).select_from(PendingMessage)) == 0
        assert await s.get(GroupMember, (gid, "bob")) is not None


async def test_optional_pending_invitee_is_never_silently_omitted_or_restricted(db):
    gid = await create(db)
    await join(db, gid, "bob")
    await change(db, gid, "invite", target_id="eve")
    snapshot = await current(db, gid)
    async with db.sessions.begin() as s:
        (await s.get(User, "eve")).suspended = True
    body = replace(fanout(snapshot, ("bob", "eve")), kind="control", invited_user_id="eve")
    with pytest.raises(DeliveryError, match="group_member_unavailable"):
        await send(db, gid, body)


async def test_last_unavailable_peer_removal_commits_empty_control_without_data_loss(db):
    gid = await create(db)
    await join(db, gid, "bob")
    async with db.sessions.begin() as s:
        (await s.get(Device, "bob-phone")).active = False
    body = replace(fanout(await current(db, gid), ()), kind="control")
    result = await atomic(db, gid, "remove", body, target_id="bob")
    assert [m["user_id"] for m in result["members"]] == ["alice"]
    assert result["control_acceptance"]["admitted"] is True
    assert result["control_acceptance"]["deliveries"] == []
    async with db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(PendingMessage)) == 0
        assert await s.scalar(select(func.count()).select_from(GroupMessage)) == 1
