"""Exercise version negotiation, opaque storage, old readers and group all-or-none admission."""

import asyncio
import base64
from datetime import timedelta
import secrets

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text

from conftest import NOW
from test_api import TestVerifier, identity
from test_groups_api import create, invite_join, settings, uid
from vipi.api import create_app
from vipi.db import Device, PendingMessage, PushOutbox, PushToken, User
from vipi.delivery import DeliveryError, MAX_UNOPENED_CHAT_EVENTS
from vipi.push import preview_envelope, preview_ticket

pytestmark = pytest.mark.asyncio
CAP = "/v1/devices/chat-features"
PENDING = "/v1/messages/pending"
READ = {"X-Vipi-Chat-Features": "1", "X-Vipi-Group-Protocol": "1"}


@pytest_asyncio.fixture
async def api(db):
    app = create_app(
        settings(groups_enabled=True, chat_features_enabled=True),
        database=db,
        verifier=TestVerifier(),
        clock=lambda: NOW,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as client:
        yield client


def payload(recipient, device):
    # Synthetic client-owned authenticated ciphertext. Its key never enters the relay.
    nonce = secrets.token_bytes(12)
    encrypted = nonce + AESGCM(AESGCM.generate_key(256)).encrypt(
        nonce, b"private event target, emoji or URL", None
    )
    return {
        "id": uid(),
        "recipient_id": recipient["id"],
        "recipient_device_id": device,
        "cipher_type": 3,
        "ciphertext": base64.b64encode(encrypted).decode(),
    }


async def enable(api, headers, version=1):
    response = await api.put(CAP, headers=headers, json={"version": version})
    assert response.status_code == 200, response.text
    assert response.json() == {"version": version, "device_id": headers["X-Vipi-Device-ID"]}


async def test_direct_downgrade_replay_rotation_and_notification_boundaries(api, db):
    profile, _, alice = await identity(api, "alice")
    bob, device, reader = await identity(api, "bob")
    path = f"/v1/people/{bob['id']}/chat-features"
    event = payload(bob, device) | {"created_at": NOW.isoformat(), "required_chat_features_version": 1}
    assert (await api.get(path, headers=alice)).json() == {"device_id": device, "version": 0}
    assert (
        await api.put(CAP, headers={"Authorization": "Bearer bob"}, json={"version": 1})
    ).status_code == 401
    await enable(api, alice)
    assert (await api.post("/v1/messages", headers=alice, json=event)).json() == {
        "error": "chat_features_unavailable"
    }
    await enable(api, reader)
    assert (await api.get(path, headers=alice)).json() == {"device_id": device, "version": 1}
    sent = await api.post("/v1/messages", headers=alice, json=event)
    assert sent.status_code == 200, sent.text
    assert (
        await api.post(f"/v1/conversations/{bob['id']}/typing", headers=alice, json={"active": True})
    ).status_code == 404
    receipt = await api.post(
        f"/v1/conversations/{profile['id']}/receipts", headers=reader, json={"seen": [event["id"]]}
    )
    assert receipt.status_code == 200
    async with db.sessions() as session:
        assert (await session.get(PendingMessage, event["id"])).state == "accepted"
    assert (await api.get(PENDING, headers=reader | READ)).json()["messages"][0]["ciphertext"] == event[
        "ciphertext"
    ]
    assert not (await api.get(PENDING, headers=reader)).json()["messages"]
    assert (await api.get(path, headers=alice)).json()["version"] == 0
    assert (await api.post("/v1/messages", headers=alice, json=event)).json() == sent.json()
    assert (
        await api.post("/v1/messages", headers=alice, json=event | {"required_chat_features_version": 0})
    ).json() == {"error": "message_id_conflict"}
    assert (await api.post("/v1/messages", headers=alice, json=event | {"id": uid()})).status_code == 409
    # Late push registration cannot queue a silent-only inbox.
    assert (
        await api.put(
            "/v1/devices/push",
            headers=reader,
            json={"provider": "apns", "environment": "sandbox", "token": "a" * 64},
        )
    ).status_code == 200
    async with db.sessions() as session:
        assert await session.get(PushOutbox, device) is None
        assert (await session.get(PendingMessage, event["id"])).ciphertext == base64.b64decode(
            event["ciphertext"]
        )
    ordinary = event | {"id": uid(), "required_chat_features_version": 0}
    assert (await api.post("/v1/messages", headers=alice, json=ordinary)).status_code == 200
    assert [item["id"] for item in (await api.get(PENDING, headers=reader)).json()["messages"]] == [
        ordinary["id"]
    ]
    async with db.sessions.begin() as session:
        # Supply strict wall-clock order so the ordinary preview depends on the prior silent event.
        (await session.get(PendingMessage, event["id"])).accepted_at = NOW - timedelta(seconds=1)
        reg = await session.get(PushToken, device)
        for msg in [ordinary, event]:
            ticket = preview_ticket("a" * 43, reg, msg["id"], NOW)
            with pytest.raises(DeliveryError, match="notification_unavailable"):
                await preview_envelope(
                    session,
                    ticket=ticket,
                    device_id=device,
                    device_secret=reader["X-Vipi-Device-Secret"],
                    secret="a" * 43,
                    now=NOW,
                )
    await enable(api, reader)
    replacement = uid()
    assert (
        await api.post(
            "/v1/devices",
            headers=reader,
            json={"device_id": replacement, "secret": secrets.token_urlsafe(32), "replace_active": True},
        )
    ).status_code == 200
    assert (await api.get(path, headers=alice)).json() == {"device_id": replacement, "version": 0}
    assert (await api.put(CAP, headers=reader, json={"version": 1})).status_code == 401
    assert (await api.post("/v1/messages", headers=alice, json=event | {"id": uid()})).json() == {
        "error": "recipient_identity_changed"
    }


async def test_group_requires_each_current_device_and_preserves_opaque_fanout(api, db):
    _, _, alice = await identity(api, "alice")
    bob, bd, bh = await identity(api, "bob")
    eve, ed, eh = await identity(api, "eve")
    group = await create(api, alice)
    group = await invite_join(api, group, alice, bob, bh)
    group = await invite_join(api, group, alice, eve, eh)
    base = "/v1/groups/" + group["id"]
    for h in [alice, bh]:
        await enable(api, h)

    def flags(doc):
        return {row["device_id"]: row["chat_features_version"] for row in doc["members"]}

    assert flags((await api.get(base, headers=alice)).json())[ed] == 0
    events = [payload(bob, bd), payload(eve, ed)]
    body = {
        "id": uid(),
        "created_at": NOW.isoformat(),
        "epoch": group["epoch"],
        "envelopes": events,
        "required_chat_features_version": 1,
    }
    async with db.sessions() as session:
        old_generations = {d: (await session.get(PushOutbox, d)).generation for d in (bd, ed)}
    assert (await api.post(base + "/messages", headers=alice, json=body)).json() == {
        "error": "chat_features_unavailable"
    }
    async with db.sessions() as session:
        for entry in events:
            assert await session.get(PendingMessage, entry["id"]) is None
    await enable(api, eh)
    assert flags((await api.get(base, headers=alice)).json())[ed] == 1
    result = await api.post(base + "/messages", headers=alice, json=body)
    assert result.status_code == 200, result.text
    async with db.sessions.begin() as session:
        for d in (bd, ed):
            assert (await session.get(PushOutbox, d)).generation == old_generations[d]
        (await session.get(Device, ed)).chat_features_v1_until = NOW
    assert flags((await api.get(base, headers=alice)).json())[ed] == 0
    assert (await api.post(base + "/messages", headers=alice, json=body)).json() == result.json()
    assert (
        await api.post(base + "/messages", headers=alice, json=body | {"required_chat_features_version": 0})
    ).json() == {"error": "group_request_conflict"}
    changed = body | {"id": uid(), "envelopes": [payload(bob, bd), payload(eve, ed)]}
    assert (await api.post(base + "/messages", headers=alice, json=changed)).json() == {
        "error": "chat_features_unavailable"
    }
    for entry, h in zip(events, [bh, eh]):
        rows = (await api.get(PENDING, headers=h | READ)).json()["messages"]
        assert [(row["group_message_id"], row["ciphertext"]) for row in rows] == [
            (body["id"], entry["ciphertext"])
        ]
        assert (await api.get(PENDING, headers=h | {"X-Vipi-Group-Protocol": "1"})).json()["messages"] == []

    removal = await api.request(
        "DELETE",
        base + "/members/" + eve["id"],
        headers=alice,
        json={"request_id": uid(), "expected_epoch": group["epoch"]},
    )
    assert removal.status_code == 200, removal.text
    await enable(api, bh)
    after = changed | {"epoch": removal.json()["epoch"], "envelopes": [payload(bob, bd)]}
    assert (await api.post(base + "/messages", headers=alice, json=after)).status_code == 200
    assert after["id"] not in {
        m.get("group_message_id") for m in (await api.get(PENDING, headers=eh | READ)).json()["messages"]
    }


async def test_bound_silent_signal_key_gap_includes_expired_entries(api, db):
    sender, sd, ah = await identity(api, "alice")
    peer, rd, rh = await identity(api, "bob")
    for h in (ah, rh):
        await enable(api, h)
    body = payload(peer, rd) | {"created_at": NOW.isoformat(), "required_chat_features_version": 1}
    async with db.sessions.begin() as session:
        for index in range(MAX_UNOPENED_CHAT_EVENTS):
            session.add(
                PendingMessage(
                    id=uid(),
                    sender_id=sender["id"],
                    sender_device_id=sd,
                    recipient_id=peer["id"],
                    recipient_device_id=rd,
                    created_at=NOW - timedelta(days=4),
                    accepted_at=NOW - timedelta(days=4),
                    expires_at=NOW - timedelta(days=1),
                    state="expired" if index % 2 else "unavailable",
                    ciphertext=None,
                    cipher_type=3,
                    fingerprint="a" * 64,
                    required_chat_features_version=1,
                )
            )
    assert (await api.post("/v1/messages", headers=ah, json=body)).json() == {
        "error": "chat_features_backlog_full"
    }
    assert (
        await api.post("/v1/messages", headers=ah, json=body | {"required_chat_features_version": 0})
    ).status_code == 200


async def test_disabled_writer_preserves_prior_accepted_events(api, db):
    _, _, sender = await identity(api, "alice")
    bob, bd, reader = await identity(api, "bob")
    for headers in (sender, reader):
        await enable(api, headers)
    event = payload(bob, bd) | {"created_at": NOW.isoformat(), "required_chat_features_version": 1}
    admitted = await api.post("/v1/messages", headers=sender, json=event)
    assert admitted.status_code == 200
    app = create_app(settings(groups_enabled=True), database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as closed:
        assert (await closed.get(f"/v1/people/{bob['id']}/chat-features", headers=sender)).json()[
            "version"
        ] == 0
        assert (await closed.post("/v1/messages", headers=sender, json=event)).json() == admitted.json()
        assert (await closed.post("/v1/messages", headers=sender, json=event | {"id": uid()})).json() == {
            "error": "chat_features_unavailable"
        }
        assert (await closed.get(PENDING, headers=reader | READ)).json()["messages"][0]["id"] == event["id"]
        assert (await closed.put(CAP, headers=reader, json={"version": 1})).json()["version"] == 0


async def test_revoke_serializes_with_waiting_admission(api, db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    _, _, sender = await identity(api, "alice")
    peer, rd, reader = await identity(api, "bob")
    for headers in (sender, reader):
        await enable(api, headers)
    event = payload(peer, rd) | {"created_at": NOW.isoformat(), "required_chat_features_version": 1}
    async with asyncio.timeout(8):
        async with db.sessions.begin() as session:
            await session.execute(select(User.id).where(User.id == peer["id"]).with_for_update())
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            task = asyncio.create_task(api.post("/v1/messages", headers=sender, json=event))
            while not await session.scalar(
                text("SELECT EXISTS (SELECT FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)))"),
                {"pid": pid},
            ):
                await session.execute(text("SELECT pg_stat_clear_snapshot()"))
                await asyncio.sleep(0.02)
            # Same write and user fence used by version-0 registration.
            (await session.get(Device, rd)).chat_features_v1_until = None
        assert (await task).json() == {"error": "chat_features_unavailable"}
    async with db.sessions() as session:
        assert await session.get(PendingMessage, event["id"]) is None
