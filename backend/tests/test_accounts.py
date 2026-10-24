from dataclasses import replace
import secrets

import pytest

from conftest import NOW
from test_delivery import message
from vipi.accounts import active_device, normalize_username, register_device, set_block
from vipi.db import Device, PendingMessage
from vipi.delivery import DeliveryError, accept, acknowledge

KEY = "service-test-" * 5


async def test_replacement_revokes_old_phone_and_destroys_old_identity_backlog(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    secret = secrets.token_urlsafe(32)
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="device_replacement_confirmation_required"):
            await register_device(s, user_id="bob", device_id="bob-new", secret=secret, replace_active=False, service_secret=KEY, now=NOW)
        await register_device(s, user_id="bob", device_id="bob-new", secret=secret, replace_active=True, service_secret=KEY, now=NOW)
    async with db.sessions.begin() as s:
        item = await s.get(PendingMessage, envelope.id)
        assert item.ciphertext is None and item.state == "identity_changed"
        assert not (await s.get(Device, "bob-phone")).active
        assert (await active_device(s, "bob", "bob-new", secret, service_secret=KEY)).active
        with pytest.raises(DeliveryError):
            await active_device(s, "alice", "bob-new", secret, service_secret=KEY)
        with pytest.raises(DeliveryError):
            await active_device(s, "bob", "bob-new", secrets.token_urlsafe(32), service_secret=KEY)
        with pytest.raises(DeliveryError, match="device_revoked"):
            await acknowledge(s, envelope.id, "bob", "bob-phone", now=NOW)
        retry = await register_device(s, user_id="bob", device_id="bob-new", secret=secret, replace_active=False, service_secret=KEY, now=NOW)
        assert retry.id == "bob-new"


async def test_revoked_sender_cannot_use_existing_message_fast_path(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
        (await s.get(Device, "alice-phone")).active = False
    async with db.sessions.begin() as s:
        with pytest.raises(DeliveryError, match="device_revoked"):
            await accept(s, envelope, now=NOW)


async def test_block_clears_backlog_and_unblocking_does_not_resurrect(db):
    envelope = message()
    async with db.sessions.begin() as s:
        await accept(s, envelope, now=NOW)
    async with db.sessions.begin() as s:
        await set_block(s, blocker_id="bob", blocked_id="alice", blocked=True)
        await set_block(s, blocker_id="bob", blocked_id="alice", blocked=True)
    async with db.sessions.begin() as s:
        item = await s.get(PendingMessage, envelope.id)
        assert item.ciphertext is None and item.state == "unavailable"
        await set_block(s, blocker_id="bob", blocked_id="alice", blocked=False)
    async with db.sessions.begin() as s:
        assert (await accept(s, envelope, now=NOW)).state == "unavailable"
        assert await acknowledge(s, envelope.id, "bob", "bob-phone", now=NOW) == "unavailable"


def test_exact_username_policy():
    assert normalize_username(" Alice_123 ") == "alice_123"
    for name in ("vBot", "security", "a", "alice@example.test", "alice\u200b", "аlice", "a" * 25):
        with pytest.raises(DeliveryError):
            normalize_username(name)
