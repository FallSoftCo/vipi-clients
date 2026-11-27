"""Atomic controls/mutation admission. Opaque bytes, not native crypto tests."""

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_groups import create, current, change, fanout, join, send, uid
from vipi import groups
from vipi.db import GroupMember, GroupMessage, GroupOperation, PendingMessage
from vipi.delivery import DeliveryError


async def atomic(db, gid, action, body, *, request_id=None, epoch=None, **extra):
    async with db.sessions.begin() as s:
        return await groups.mutate(
            s,
            group_id=gid,
            actor_id="alice",
            device_id="alice-phone",
            request_id=request_id or uid(),
            expected_epoch=body.epoch if epoch is None else epoch,
            action=action,
            control=body,
            now=NOW,
            **extra,
        )


async def test_atomic_remove_binds_exact_controls_and_retries_without_readmission(db):
    gid = await create(db)
    await join(db, gid, "bob")
    await join(db, gid, "eve")
    body = replace(fanout(await current(db, gid)), kind="control")
    request = uid()
    result = await atomic(db, gid, "remove", body, request_id=request, target_id="bob")
    assert {m["user_id"] for m in result["members"]} == {"alice", "eve"}
    assert result["control_acceptance"]["admitted"] is True
    assert [d["state"] for d in result["control_acceptance"]["deliveries"]] == [
        "unavailable",
        "accepted",
    ]
    retry = await atomic(db, gid, "remove", body, request_id=request, target_id="bob")
    assert retry == result
    tampered = replace(
        body,
        envelopes=(
            replace(body.envelopes[0], ciphertext=b"changed" * 12),
            body.envelopes[1],
        ),
    )
    with pytest.raises(DeliveryError, match="group_request_conflict"):
        await atomic(db, gid, "remove", tampered, request_id=request, target_id="bob")
    async with db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(GroupMessage)) == 1


async def test_stale_mutation_cannot_publish_its_control(db):
    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    await change(db, gid, "rename", title="Concurrent rename")
    request = uid()
    with pytest.raises(DeliveryError, match="group_epoch_changed"):
        await atomic(
            db, gid, "role", body, request_id=request, target_id="bob", role="admin"
        )
    async with db.sessions() as s:
        assert await s.get(GroupMessage, (gid, body.id)) is None
        assert await s.get(GroupOperation, (gid, request)) is None
        assert await s.get(PendingMessage, body.envelopes[0].id) is None
        assert (await s.get(GroupMember, (gid, "bob"))).role == "member"


async def test_failed_permission_after_control_admission_rolls_back_even_if_caught(db):
    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    request = uid()
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="group_permission_denied"):
            await groups.mutate(
                s,
                group_id=gid,
                actor_id="alice",
                device_id="alice-phone",
                request_id=request,
                expected_epoch=body.epoch,
                action="role",
                target_id="alice",
                role="admin",
                control=body,
                now=NOW,
            )
    async with db.sessions() as s:
        assert await s.get(GroupMessage, (gid, body.id)) is None
        assert await s.get(GroupOperation, (gid, request)) is None
        assert await s.get(PendingMessage, body.envelopes[0].id) is None


async def test_atomic_final_owner_leave_can_retry_after_closure_and_offline_expiry(db):
    gid = await create(db)
    body = replace(fanout(await current(db, gid), ()), kind="control")
    request = uid()
    result = await atomic(db, gid, "leave", body, request_id=request)
    assert result["left"] is True and result["control_acceptance"]["admitted"] is True
    assert await atomic(db, gid, "leave", body, request_id=request) == result
    async with db.sessions.begin() as s:
        await groups.expire(s, now=NOW + timedelta(days=11))
    # Control admission metadata lives as long as mutation retry receipts.
    assert await atomic(db, gid, "leave", body, request_id=request) == result


async def test_previously_standalone_control_cannot_be_retroactively_called_atomic(db):
    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    await send(db, gid, body)
    with pytest.raises(DeliveryError, match="group_control_already_admitted"):
        await atomic(db, gid, "role", body, target_id="bob", role="admin")
    assert (
        next(m for m in (await current(db, gid))["members"] if m["user_id"] == "bob")[
            "role"
        ]
        == "member"
    )


async def test_configured_queue_cap_applies_to_atomic_controls(db):
    from vipi.delivery import Envelope, accept

    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    async with db.sessions.begin() as s:
        await accept(
            s,
            Envelope(uid(), "eve", "eve-phone", "bob", "bob-phone", NOW, b"x" * 64),
            now=NOW,
        )
    request = uid()
    with pytest.raises(DeliveryError, match="recipient_queue_full"):
        async with db.sessions.begin() as s:
            await groups.mutate(
                s,
                group_id=gid,
                actor_id="alice",
                device_id="alice-phone",
                request_id=request,
                expected_epoch=body.epoch,
                action="role",
                target_id="bob",
                role="admin",
                control=body,
                now=NOW,
                max_pending=1,
            )
    assert (
        next(m for m in (await current(db, gid))["members"] if m["user_id"] == "bob")[
            "role"
        ]
        == "member"
    )


async def test_revoked_device_cannot_retrieve_or_apply_atomic_mutation(db):
    from vipi.db import Device

    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    async with db.sessions.begin() as s:
        (await s.get(Device, "alice-phone")).active = False
    with pytest.raises(DeliveryError, match="device_revoked"):
        await atomic(db, gid, "role", body, target_id="bob", role="admin")
