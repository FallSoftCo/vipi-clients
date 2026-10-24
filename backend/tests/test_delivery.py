from dataclasses import replace
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from vipi.db import Block, Device, PendingMessage
from vipi.delivery import Envelope, DeliveryError, accept, acknowledge, expire, utc
from conftest import NOW


def message():
    # Opaque bytes exercise relay behavior; these are not an encryption test.
    return Envelope(str(uuid4()), "alice", "alice-phone", "bob", "bob-phone", NOW, b"x" * 64)


async def test_retry_keeps_deadline_and_content(db):
    envelope = message()
    async with db.sessions.begin() as s:
        first = await accept(s, envelope, now=NOW)
        deadline = first.expires_at
    async with db.sessions.begin() as s:
        retry = await accept(s, envelope, now=NOW + timedelta(hours=60))
        assert utc(retry.expires_at) == deadline
        assert retry.ciphertext == envelope.ciphertext
    async with db.sessions.begin() as s:
        expired = await accept(s, envelope, now=NOW + timedelta(hours=72))
        assert expired.state == "expired" and expired.ciphertext is None


async def test_reusing_id_with_new_body_or_timestamp_fails(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    for changed in (replace(envelope, ciphertext=b"y" * 64), replace(envelope, created_at=NOW + timedelta(seconds=1))):
        async with db.sessions.begin() as s:
            with pytest.raises(DeliveryError, match="message_id_conflict"):
                await accept(s, changed, now=NOW + timedelta(seconds=1))


async def test_only_exact_recipient_device_can_acknowledge(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError):
            await acknowledge(s, envelope.id, "eve", "eve-phone", now=NOW)
        with pytest.raises(DeliveryError):
            await acknowledge(s, envelope.id, "bob", "other-phone", now=NOW)
        assert await acknowledge(s, envelope.id, "bob", "bob-phone", now=NOW) == "delivered"
        assert (await s.get(PendingMessage, envelope.id)).ciphertext is None
    async with db.sessions.begin() as s:
        assert (await accept(s, envelope, now=NOW + timedelta(hours=1))).state == "delivered"
        assert await acknowledge(s, envelope.id, "bob", "bob-phone", now=NOW) == "delivered"


async def test_expiry_removes_body_even_without_any_client_retry(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    async with db.sessions.begin() as s:
        assert await expire(s, now=NOW + timedelta(hours=72)) == 1
    async with db.sessions.begin() as s:
        item = await s.get(PendingMessage, envelope.id)
        assert item.ciphertext is None and item.state == "expired"
        assert await acknowledge(s, envelope.id, "bob", "bob-phone", now=NOW + timedelta(hours=73)) == "expired"


async def test_cannot_resurrect_after_metadata_purge(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    async with db.sessions.begin() as s:
        await expire(s, now=NOW + timedelta(days=11))
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="message_expired"):
            await accept(s, envelope, now=NOW + timedelta(days=11))


async def test_block_queue_limit_and_device_replacement(db):
    async with db.sessions.begin() as s:
        s.add(Block(blocker_id="bob", blocked_id="alice"))
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="recipient_unavailable"):
            await accept(s, message(), now=NOW)
    async with db.sessions.begin() as s:
        await s.delete(await s.get(Block, ("bob", "alice")))
        await accept(s, message(), now=NOW, max_pending=1)
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="recipient_queue_full"):
            await accept(s, message(), now=NOW, max_pending=1)
        (await s.get(Device, "bob-phone")).active = False
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="recipient_identity_changed"):
            await accept(s, message(), now=NOW)


async def test_clock_skew_cannot_extend_server_ttl(db):
    envelope = replace(message(), created_at=NOW + timedelta(minutes=4))
    async with db.sessions.begin() as s:
        item = await accept(s, envelope, now=NOW)
        assert item.expires_at == NOW + timedelta(hours=72)
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="clock_ahead"):
            await accept(s, replace(message(), created_at=NOW + timedelta(minutes=6)), now=NOW)
