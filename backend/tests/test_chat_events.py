import asyncio
import base64
import json
import os
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, update
from conftest import NOW
from test_api import identity
from test_events import Socket, application
from vipi.db import Device, PendingMessage, PushOutbox
from vipi.events import EventQueue, InboxEvents, notify_chat


async def send(client, headers, recipient, device):
    value = {
        "id": str(uuid4()),
        "recipient_id": recipient["id"],
        "recipient_device_id": device,
        "created_at": NOW.isoformat(),
        "cipher_type": 3,
        "ciphertext": base64.b64encode(b"synthetic opaque envelope" * 3).decode(),
    }
    result = await client.post("/v1/messages", headers=headers, json=value)
    assert result.status_code == 200, result.text
    return value["id"]


def test_coalescing_is_bounded_and_legacy_queue_ignores_chat_events():
    old, new = EventQueue(), EventQueue(True)
    peer = str(uuid4())
    for active in (True, False, True, False):
        event = {"event": "typing", "peer": peer, "active": active}
        old.put_nowait(event)
        new.put_nowait(event)
    assert old.empty()
    assert new.get_nowait() == {"event": "typing", "peer": peer, "active": False}
    for _ in range(100):
        new.put_nowait({"event": "receipts_changed", "peer": peer})
    assert len(new.pending) == 1
    assert new.get_nowait() == {"event": "receipts_changed", "peer": peer}
    for _ in range(200):
        new.put_nowait({"event": "typing", "peer": str(uuid4()), "active": True})
    new.put_nowait("inbox_changed")
    assert len(new.pending) == 32 and "inbox_changed" in new.pending.values()
    # A busy conversation cannot evict the durable inbox catch-up signal.
    for _ in range(100):
        new.put_nowait({"event": "receipts_changed", "peer": str(uuid4())})
    new.put_nowait({"event": "typing", "peer": peer, "active": True})
    assert "inbox_changed" in new.pending.values()
    new.put_nowait(None)
    assert new.get_nowait() is None and new.empty()


async def test_strict_notification_payload_preserves_old_wire_protocol(db):
    broker = InboxEvents(db)
    broker.ready.set()
    device, peer = str(uuid4()), str(uuid4())
    old, new = broker.subscribe(device), broker.subscribe(device, chat_events=True)
    old.get_nowait()
    new.get_nowait()
    bad = [
        {},
        None,
        {"device": None},
        {"device": device, "event": "typing", "peer": peer, "active": "yes"},
        {
            "device": device,
            "event": "typing",
            "peer": peer,
            "active": True,
            "text": "forbidden",
        },
    ]
    for item in bad:
        broker.dispatch(json.dumps(item))
    assert old.empty() and new.empty()
    broker.dispatch(
        json.dumps({"device": device, "event": "typing", "peer": peer, "active": True})
    )
    assert old.empty() and new.get_nowait() == {
        "event": "typing",
        "peer": peer,
        "active": True,
    }
    broker.dispatch(device)
    assert old.get_nowait() == new.get_nowait() == "inbox_changed"
    broker.unsubscribe(device, old)
    broker.unsubscribe(device, new)


async def test_typing_requires_relationship_and_current_unblocked_devices(db):
    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        path = f"/v1/conversations/{bob['id']}/typing"
        assert (
            await client.post(path, headers=ah, json={"active": True})
        ).status_code == 404
        await send(client, ah, bob, bd)
        assert (await client.post(path, headers=ah, json={"active": True})).json() == {
            "accepted": True
        }
        assert (
            await client.post(path, headers=ah, json={"active": False})
        ).status_code == 200
        for body in ({"active": "yes"}, {"active": True, "text": "forbidden"}):
            assert (await client.post(path, headers=ah, json=body)).status_code == 422
        assert (
            await client.post(
                path,
                headers=ah | {"X-Vipi-Device-Secret": "x" * 43},
                json={"active": True},
            )
        ).status_code == 401
        await client.put(
            "/v1/blocks/" + alice["id"], headers=bh, json={"blocked": True}
        )
        assert (
            await client.post(path, headers=ah, json={"active": False})
        ).status_code == 404
        await client.put(
            "/v1/blocks/" + alice["id"], headers=bh, json={"blocked": False}
        )
        async with db.sessions.begin() as session:
            await session.execute(
                update(Device).where(Device.id == bd).values(active=False)
            )
            session.add(
                Device(
                    id=str(uuid4()),
                    user_id=bob["id"],
                    credential_hash="a" * 64,
                    active=True,
                    created_at=NOW,
                )
            )
        assert (
            await client.post(path, headers=ah, json={"active": True})
        ).status_code == 404


async def test_seen_before_delivery_ack_is_read_but_legacy_is_delivered(db):
    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        _, _, eh = await identity(client, "eve")
        mid = await send(client, ah, bob, bd)
        bp = f"/v1/conversations/{alice['id']}/receipts"
        ap = f"/v1/conversations/{bob['id']}/receipts"
        for headers in (ah, eh):
            assert (
                await client.post(
                    ap, headers=headers, json={"seen": [mid], "check": [mid]}
                )
            ).json() == {"acknowledged": [mid], "read": []}
        assert (
            await client.post(bp, headers=bh, json={"seen": [mid, mid], "check": [mid]})
        ).json() == {"acknowledged": [mid], "read": []}
        async with db.sessions() as session:
            row = await session.get(PendingMessage, mid)
            assert row.state == "read" and row.ciphertext is None
        assert (await client.post(ap, headers=ah, json={"check": [mid]})).json() == {
            "acknowledged": [],
            "read": [mid],
        }
        assert (await client.get("/v1/messages/" + mid, headers=ah)).json()[
            "state"
        ] == "delivered"
        assert (
            await client.post("/v1/messages/" + mid + "/receipt", headers=bh)
        ).json()["state"] == "delivered"
        assert (await client.get("/v1/messages/pending", headers=bh)).json()[
            "messages"
        ] == []
        results = await asyncio.gather(
            client.post(bp, headers=bh, json={"seen": [mid]}),
            client.post("/v1/messages/" + mid + "/receipt", headers=bh),
        )
        assert all(item.status_code == 200 for item in results)


async def test_receipt_scoping_and_indistinguishable_noops(db):
    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        eve, ed, eh = await identity(client, "eve")
        mid = await send(client, ah, bob, bd)
        other = await send(client, eh, bob, bd)
        missing = str(uuid4())
        bp = f"/v1/conversations/{alice['id']}/receipts"
        assert (
            await client.post(
                bp,
                headers=bh,
                json={"seen": [missing, other, mid], "check": [mid, other]},
            )
        ).json() == {"acknowledged": [missing, other, mid], "read": []}
        async with db.sessions.begin() as session:
            assert (await session.get(PendingMessage, other)).state == "accepted"
            row = await session.get(PendingMessage, mid)
            row.sender_device_id = str(uuid4())
        ap = f"/v1/conversations/{bob['id']}/receipts"
        assert (await client.post(ap, headers=ah, json={"check": [mid]})).json()[
            "read"
        ] == []
        await client.put(
            "/v1/blocks/" + alice["id"], headers=bh, json={"blocked": True}
        )
        body = {"seen": [mid, other, missing], "check": [mid]}
        blocked = await client.post(bp, headers=bh, json=body)
        unknown = await client.post(
            "/v1/conversations/" + str(uuid4()) + "/receipts", headers=bh, json=body
        )
        assert (
            blocked.json()
            == unknown.json()
            == {"acknowledged": [mid, other, missing], "read": []}
        )


async def test_expired_seen_is_not_written_and_requests_are_bounded(db):
    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        mid = await send(client, ah, bob, bd)
        async with db.sessions.begin() as session:
            row = await session.get(PendingMessage, mid)
            row.expires_at = NOW - timedelta(seconds=1)
            original = row.ciphertext
        path = f"/v1/conversations/{alice['id']}/receipts"
        assert (await client.post(path, headers=bh, json={"seen": [mid]})).json() == {
            "acknowledged": [mid],
            "read": [],
        }
        async with db.sessions() as session:
            row = await session.get(PendingMessage, mid)
            assert row.state == "accepted" and row.ciphertext == original
        for field in ("seen", "check"):
            assert (
                await client.post(
                    path, headers=bh, json={field: [str(uuid4()) for _ in range(65)]}
                )
            ).status_code == 422
        for body in ({"seen": ["bad"]}, {"seen": [], "text": "forbidden"}):
            assert (await client.post(path, headers=bh, json=body)).status_code == 422
        assert (await client.post(path, json={"seen": []})).status_code == 401


async def test_queued_events_recheck_blocks_and_own_device(db):
    async with application(db) as (app, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        await send(client, ah, bob, bd)
        async with Socket(app, bh | {"X-Vipi-Chat-Events": "1"}) as recipient:
            await recipient.next()
            await client.put(
                "/v1/blocks/" + alice["id"], headers=bh, json={"blocked": True}
            )
            app.state.events.publish(
                bd, {"event": "typing", "peer": alice["id"], "active": True}
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(recipient.next(), 0.1)
            app.state.events.publish(bd)
            assert json.loads((await recipient.next())["text"]) == {
                "event": "inbox_changed"
            }
            async with db.sessions.begin() as session:
                await session.execute(
                    update(Device).where(Device.id == bd).values(active=False)
                )
            app.state.events.publish(
                bd, {"event": "receipts_changed", "peer": alice["id"]}
            )
            assert (await recipient.next())["code"] == 4403


@pytest.mark.skipif(
    not os.environ.get("VIPI_TEST_POSTGRES_URL"),
    reason="actual cross-worker PostgreSQL",
)
async def test_cross_worker_chat_events_and_old_socket_compatibility(db):
    async with application(db) as (one, client), application(db) as (two, other_client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        async with (
            Socket(one, ah | {"X-Vipi-Chat-Events": "1"}) as sender,
            Socket(two, ah) as old_sender,
            Socket(two, bh | {"X-Vipi-Chat-Events": "1"}) as recipient,
            Socket(one, bh) as old_recipient,
        ):
            for socket in (sender, old_sender, recipient, old_recipient):
                await socket.next()
            mid = await send(client, ah, bob, bd)
            for socket in (recipient, old_recipient):
                assert json.loads((await socket.next())["text"]) == {
                    "event": "inbox_changed"
                }
            path = f"/v1/conversations/{bob['id']}/typing"
            assert (
                await client.post(path, headers=ah, json={"active": True})
            ).status_code == 200
            assert json.loads((await recipient.next())["text"]) == {
                "event": "typing",
                "peer": alice["id"],
                "active": True,
            }
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(old_recipient.next(), 0.1)
            assert (
                await client.post(path, headers=ah, json={"active": False})
            ).status_code == 200
            assert json.loads((await recipient.next())["text"])["active"] is False
            seen = await other_client.post(
                f"/v1/conversations/{alice['id']}/receipts",
                headers=bh,
                json={"seen": [mid]},
            )
            assert seen.json() == {"acknowledged": [mid], "read": []}
            assert json.loads((await old_sender.next())["text"]) == {
                "event": "inbox_changed"
            }
            events = [json.loads((await sender.next())["text"]) for _ in range(2)]
            assert {"event": "inbox_changed"} in events and {
                "event": "receipts_changed",
                "peer": bob["id"],
            } in events
            assert (
                await client.post(
                    f"/v1/conversations/{bob['id']}/receipts",
                    headers=ah,
                    json={"check": [mid]},
                )
            ).json()["read"] == [mid]
            async with db.sessions() as session:
                assert len((await session.scalars(select(PushOutbox))).all()) <= 1


@pytest.mark.skipif(
    not os.environ.get("VIPI_TEST_POSTGRES_URL"), reason="actual transactional NOTIFY"
)
async def test_structured_notifications_commit_and_rollback(db):
    first, second = InboxEvents(db), InboxEvents(db)
    await first.start()
    await second.start()
    device, peer = str(uuid4()), str(uuid4())
    queue = second.subscribe(device, chat_events=True)
    queue.get_nowait()
    event = {"event": "typing", "peer": peer, "active": True}
    try:
        async with db.sessions.begin() as session:
            await notify_chat(session, device, event)
            assert queue.empty()
        assert await asyncio.wait_for(queue.get(), 3) == event
        with pytest.raises(ValueError):
            async with db.sessions.begin() as session:
                await notify_chat(session, device, event)
                raise ValueError("rollback")
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(queue.get(), 0.1)
    finally:
        second.unsubscribe(device, queue)
        await first.close()
        await second.close()


async def test_typing_rate_bound_does_not_create_messages_or_push_jobs(db):
    from vipi.db import RateWindow

    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        mid = await send(client, ah, bob, bd)
        async with db.sessions() as session:
            push_before = len((await session.scalars(select(PushOutbox))).all())
        path = f"/v1/conversations/{bob['id']}/typing"
        for _ in range(60):
            result = await client.post(path, headers=ah, json={"active": True})
            assert result.status_code == 200
        assert (
            await client.post(path, headers=ah, json={"active": False})
        ).status_code == 429
        async with db.sessions() as session:
            messages = (await session.scalars(select(PendingMessage))).all()
            assert len(messages) == 1 and messages[0].id == mid
            assert (
                messages[0].state == "accepted" and messages[0].ciphertext is not None
            )
            assert len((await session.scalars(select(PushOutbox))).all()) == push_before
            rates = (
                await session.scalars(
                    select(RateWindow).where(RateWindow.scope == "chat-typing")
                )
            ).all()
            assert len(rates) == 1 and rates[0].count == 60


@pytest.mark.skipif(
    not os.environ.get("VIPI_TEST_POSTGRES_URL"), reason="actual row-lock concurrency"
)
async def test_explicit_seen_races_ordinary_ack_without_losing_read_state(db):
    async with application(db) as (_, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        mids = [await send(client, ah, bob, bd) for _ in range(5)]
        for mid in mids:
            seen, ack = await asyncio.gather(
                client.post(
                    f"/v1/conversations/{alice['id']}/receipts",
                    headers=bh,
                    json={"seen": [mid]},
                ),
                client.post(f"/v1/messages/{mid}/receipt", headers=bh),
            )
            assert seen.json() == {"acknowledged": [mid], "read": []}
            assert ack.json()["state"] == "delivered"
        async with db.sessions() as session:
            rows = (await session.scalars(select(PendingMessage))).all()
            assert len(rows) == 5 and all(
                row.state == "read" and row.ciphertext is None for row in rows
            )
