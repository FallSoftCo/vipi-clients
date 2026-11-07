import asyncio
from datetime import timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from conftest import NOW
from test_delivery import message
from test_subscriptions import settings
from vipi.accounts import register_device
from vipi.db import PushOutbox, PushToken
from vipi.delivery import accept, acknowledge
from vipi.push import enqueue, process_pushes, PushProviders, register, token_cipher


async def seed(db):
    async with db.sessions.begin() as session:
        await register(session, user_id="bob", device_id="bob-phone", provider="fcm", environment="production",
            token="opaque-registration-token", secret="a"*43, now=NOW)
        item = await accept(session, message(), now=NOW)
        await enqueue(session, item.recipient_device_id, NOW, item.expires_at)
        return item.id


class Provider:
    def __init__(self, outcome="sent"):
        self.outcome, self.calls = outcome, []
    async def send(self, registration, token, now, expires_at):
        self.calls.append((registration.device_id, token))
        return self.outcome


async def test_pushes_coalesce_encrypt_token_and_remove_on_device_replacement(db):
    await seed(db)
    async with db.sessions.begin() as session:
        await enqueue(session, "bob-phone", NOW, NOW+timedelta(hours=72))
    async with db.sessions() as session:
        rows = (await session.execute(select(PushOutbox))).scalars().all()
        assert len(rows) == 1 and rows[0].generation == 2
        token = await session.get(PushToken, "bob-phone")
        assert b"opaque-registration-token" not in token.token
        assert token_cipher("a"*43).decrypt(token.token) == b"opaque-registration-token"
    provider = Provider()
    assert (await process_pushes(db, provider, secret="a"*43, now=NOW))["sent"] == 1
    assert len(provider.calls) == 1
    async with db.sessions.begin() as session:
        await register_device(session, user_id="bob", device_id="bob-new", secret="c"*43,
            replace_active=True, service_secret="a"*43, now=NOW)
        assert await session.get(PushToken, "bob-phone") is None
        assert await session.get(PushOutbox, "bob-phone") is None


async def test_delivered_inbox_does_not_generate_stale_notification(db):
    message_id = await seed(db)
    async with db.sessions.begin() as session:
        await acknowledge(session, message_id, "bob", "bob-phone", now=NOW)
    provider = Provider()
    result = await process_pushes(db, provider, secret="a"*43, now=NOW)
    assert result["discarded"] == 1 and not provider.calls


async def test_new_message_during_provider_call_survives_old_job_completion(db):
    await seed(db)
    started, release = asyncio.Event(), asyncio.Event()
    class Slow:
        async def send(self, registration, token, now, expires_at):
            started.set()
            await release.wait()
            return "sent"
    task = asyncio.create_task(process_pushes(db, Slow(), secret="a"*43, now=NOW, limit=1))
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with db.sessions.begin() as session:
            await enqueue(session, "bob-phone", NOW+timedelta(seconds=1), NOW+timedelta(hours=72))
    finally:
        release.set()
    assert (await task)["sent"] == 1
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.generation == 2 and job.lease_token is None


async def test_transient_failure_retries_but_definitive_invalid_retires_token(db):
    await seed(db)
    assert (await process_pushes(db, Provider("retry"), secret="a"*43, now=NOW))["retry"] == 1
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.next_attempt_at.replace(tzinfo=NOW.tzinfo) > NOW
        assert await session.get(PushToken, "bob-phone")
    assert (await process_pushes(db, Provider("invalid"), secret="a"*43, now=NOW+timedelta(minutes=1)))["invalid"] == 1
    async with db.sessions() as session:
        assert await session.get(PushToken, "bob-phone") is None
        assert await session.get(PushOutbox, "bob-phone") is None


async def test_fcm_payload_has_no_conversation_content_or_identity():
    captured = []
    def handler(request):
        import json
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"name": "projects/fixture/messages/1"})
    providers = PushProviders(settings(fcm_project_id="fixture"), transport=httpx.MockTransport(handler),
        credentials=SimpleNamespace(valid=True, token="fixture-credential"))
    try:
        assert await providers.send(SimpleNamespace(provider="fcm"), "fixture-device-token", NOW, NOW+timedelta(hours=72)) == "sent"
        payload = captured[0]["message"]
        assert payload["data"] == {"kind": "inbox_changed"}
        assert "notification" not in payload and payload["android"]["ttl"] == "3600s"
    finally:
        await providers.close()
