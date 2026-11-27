"""Durable cancellation and immutable outcome tests; no crypto certification."""

from dataclasses import replace
from datetime import timedelta
import pytest
from conftest import NOW
from test_groups import create, change, current, fanout, join, uid
from vipi import groups
from vipi.db import GroupCancellation, GroupOperation, PendingMessage
from vipi.delivery import DeliveryError


async def cancel(
    db,
    gid,
    request,
    *,
    action="rename",
    epoch=1,
    actor="alice",
    device=None,
    at=NOW,
    **fields,
):
    async with db.sessions.begin() as session:
        return await groups.cancel_operation(
            session,
            group_id=gid,
            actor_id=actor,
            request_id=request,
            action=action,
            expected_epoch=epoch,
            original_device_id=device or actor + "-phone",
            device_id=actor + "-phone",
            now=at,
            **fields,
        )


async def test_cancelled_mutation_cannot_arrive_late_and_descriptor_stays_exact(db):
    gid, request = await create(db), uid()
    result = await cancel(db, gid, request, title="Prepared name")
    assert result == {
        "status": "cancelled",
        "request_id": request,
        "group_id": gid,
        "expected_epoch": 1,
    }
    assert await cancel(db, gid, request, title="Prepared name") == result
    with pytest.raises(DeliveryError, match="group_operation_cancelled"):
        await change(
            db,
            gid,
            "rename",
            request_id=request,
            epoch=1,
            title="Prepared name",
            device_id="alice-phone",
        )
    with pytest.raises(DeliveryError, match="group_request_conflict"):
        await change(
            db,
            gid,
            "rename",
            request_id=request,
            epoch=1,
            title="Different",
            device_id="alice-phone",
        )
    with pytest.raises(DeliveryError, match="group_request_conflict"):
        await cancel(db, gid, request, title="Different")
    assert (await current(db, gid))["title"] == "Friends"


async def test_admitted_original_snapshot_is_not_replaced_by_later_roster(db):
    gid, request = await create(db), uid()
    original = await change(
        db,
        gid,
        "rename",
        request_id=request,
        epoch=1,
        title="First",
        device_id="alice-phone",
    )
    await join(db, gid, "bob")
    resolved = await cancel(db, gid, request, title="First")
    assert resolved["status"] == "admitted" and resolved["result"] == original
    assert (
        len(original["members"]) == 1 and len((await current(db, gid))["members"]) == 2
    )
    assert (
        await change(
            db,
            gid,
            "rename",
            request_id=request,
            epoch=1,
            title="First",
            device_id="alice-phone",
        )
        == original
    )


async def test_legacy_receipt_never_fabricates_an_original_result(db):
    gid, request = await create(db), uid()
    async with db.sessions.begin() as session:
        session.add(
            GroupOperation(
                group_id=gid,
                request_id=request,
                actor_id="alice",
                fingerprint=groups.digest(["rename", 1, None, "Legacy", None, None]),
                created_at=NOW,
            )
        )
    with pytest.raises(DeliveryError, match="group_operation_outcome_unavailable"):
        await cancel(db, gid, request, title="Legacy")
    with pytest.raises(DeliveryError, match="group_operation_outcome_unavailable"):
        await change(
            db,
            gid,
            "rename",
            request_id=request,
            epoch=1,
            title="Legacy",
            device_id="alice-phone",
        )


async def test_current_epoch_fence_survives_arbitrary_time_but_stale_epoch_can_clean(
    db,
):
    gid, request = await create(db), uid()
    await cancel(db, gid, request, title="Prepared")
    async with db.sessions.begin() as session:
        await groups.expire(session, now=NOW + timedelta(days=3650))
        assert await session.get(GroupCancellation, (gid, "alice", request))
    await change(db, gid, "rename", title="New epoch", epoch=1, device_id="alice-phone")
    async with db.sessions.begin() as session:
        await groups.expire(session, now=NOW + timedelta(days=3650))
        assert await session.get(GroupCancellation, (gid, "alice", request)) is None
    with pytest.raises(DeliveryError, match="group_epoch_changed"):
        await change(
            db,
            gid,
            "rename",
            request_id=request,
            epoch=1,
            title="Prepared",
            device_id="alice-phone",
        )


async def test_control_cancel_binds_original_envelopes_and_never_admits_any_ciphertext(
    db,
):
    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    await cancel(db, gid, body.id, action="control", epoch=body.epoch, control=body)
    with pytest.raises(DeliveryError, match="group_operation_cancelled"):
        async with db.sessions.begin() as session:
            await groups.send(
                session,
                group_id=gid,
                actor_id="alice",
                device_id="alice-phone",
                fanout=body,
                now=NOW,
            )
    altered = replace(
        body, envelopes=(replace(body.envelopes[0], ciphertext=b"z" * 64),)
    )
    with pytest.raises(DeliveryError, match="group_request_conflict"):
        await cancel(
            db, gid, body.id, action="control", epoch=body.epoch, control=altered
        )
    async with db.sessions() as session:
        assert await session.get(PendingMessage, body.envelopes[0].id) is None


async def test_unrelated_actor_cannot_cancel_or_read_someone_elses_outcome(db):
    gid, request = await create(db), uid()
    await change(
        db,
        gid,
        "rename",
        request_id=request,
        epoch=1,
        title="Private outcome",
        device_id="alice-phone",
    )
    with pytest.raises(DeliveryError, match="group_request_conflict"):
        await cancel(db, gid, request, actor="eve", title="Private outcome")
    with pytest.raises(DeliveryError, match="group_unavailable"):
        await cancel(db, gid, uid(), actor="eve", action="leave", epoch=2)


async def test_expired_control_fence_cleans_only_after_immutable_expiry_prevents_late_send(
    db,
):
    gid = await create(db)
    await join(db, gid, "bob")
    body = replace(fanout(await current(db, gid), ("bob",)), kind="control")
    await cancel(db, gid, body.id, action="control", epoch=body.epoch, control=body)
    at = NOW + timedelta(hours=72)
    async with db.sessions.begin() as session:
        await groups.expire(session, now=at)
        assert await session.get(GroupCancellation, (gid, "alice", body.id)) is None
    with pytest.raises(DeliveryError, match="message_expired"):
        async with db.sessions.begin() as session:
            await groups.send(
                session,
                group_id=gid,
                actor_id="alice",
                device_id="alice-phone",
                fanout=body,
                now=at,
            )


async def test_actor_bound_fence_does_not_prevent_another_members_own_operation(db):
    gid = await create(db)
    await join(db, gid, "bob")
    epoch = (await current(db, gid))["epoch"]
    request = uid()
    original = await cancel(db, gid, request, action="leave", epoch=epoch)
    assert await change(
        db,
        gid,
        "leave",
        actor="bob",
        request_id=request,
        epoch=epoch,
        device_id="bob-phone",
    ) == {"left": True}
    assert await cancel(db, gid, request, action="leave", epoch=epoch) == original


async def test_bounded_current_epoch_fences_exhaust_explicitly_without_forgetting_old_requests(
    db,
):
    gid = await create(db)
    requests = [uid() for _ in range(256)]
    async with db.sessions.begin() as session:
        for request in requests:
            session.add(
                GroupCancellation(
                    group_id=gid,
                    actor_id="alice",
                    request_id=request,
                    fingerprint=groups.digest(
                        ["rename", 1, None, "Prepared", None, None]
                    ),
                    expected_epoch=1,
                    original_device_id="alice-phone",
                    created_at=NOW,
                )
            )
    with pytest.raises(DeliveryError, match="group_cancellation_limit"):
        await cancel(db, gid, uid(), title="More")
    with pytest.raises(DeliveryError, match="group_operation_cancelled"):
        await change(
            db,
            gid,
            "rename",
            request_id=requests[0],
            epoch=1,
            title="Prepared",
            device_id="alice-phone",
        )
    async with db.sessions.begin() as session:
        await groups.revoke_memberships(session, "alice", now=NOW, deleting=True)
        from sqlalchemy import select, func

        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupCancellation)
                .where(GroupCancellation.actor_id == "alice")
            )
            == 0
        )
