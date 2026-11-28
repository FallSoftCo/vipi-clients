import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
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
        await register(
            session,
            user_id="bob",
            device_id="bob-phone",
            provider="fcm",
            environment="production",
            token="opaque-registration-token",
            secret="a" * 43,
            now=NOW,
        )
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
        await enqueue(session, "bob-phone", NOW, NOW + timedelta(hours=72))
    async with db.sessions() as session:
        rows = (await session.execute(select(PushOutbox))).scalars().all()
        assert len(rows) == 1 and rows[0].generation == 2
        token = await session.get(PushToken, "bob-phone")
        assert b"opaque-registration-token" not in token.token
        assert (
            token_cipher("a" * 43).decrypt(token.token) == b"opaque-registration-token"
        )
    provider = Provider()
    assert (await process_pushes(db, provider, secret="a" * 43, now=NOW))["sent"] == 1
    assert len(provider.calls) == 1
    async with db.sessions.begin() as session:
        await register_device(
            session,
            user_id="bob",
            device_id="bob-new",
            secret="c" * 43,
            replace_active=True,
            service_secret="a" * 43,
            now=NOW,
        )
        assert await session.get(PushToken, "bob-phone") is None
        assert await session.get(PushOutbox, "bob-phone") is None


async def test_delivered_inbox_does_not_generate_stale_notification(db):
    message_id = await seed(db)
    async with db.sessions.begin() as session:
        await acknowledge(session, message_id, "bob", "bob-phone", now=NOW)
    provider = Provider()
    result = await process_pushes(db, provider, secret="a" * 43, now=NOW)
    assert result["discarded"] == 1 and not provider.calls


async def test_new_message_during_provider_call_survives_old_job_completion(db):
    await seed(db)
    started, release = asyncio.Event(), asyncio.Event()

    class Slow:
        async def send(self, registration, token, now, expires_at):
            started.set()
            await release.wait()
            return "sent"

    task = asyncio.create_task(
        process_pushes(db, Slow(), secret="a" * 43, now=NOW, limit=1)
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with db.sessions.begin() as session:
            await enqueue(
                session,
                "bob-phone",
                NOW + timedelta(seconds=1),
                NOW + timedelta(hours=72),
            )
    finally:
        release.set()
    assert (await task)["sent"] == 1
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.generation == 2 and job.lease_token is None


async def test_transient_failure_retries_but_definitive_invalid_retires_token(db):
    await seed(db)
    assert (await process_pushes(db, Provider("retry"), secret="a" * 43, now=NOW))[
        "retry"
    ] == 1
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.next_attempt_at.replace(tzinfo=NOW.tzinfo) > NOW
        assert await session.get(PushToken, "bob-phone")
    assert (
        await process_pushes(
            db, Provider("invalid"), secret="a" * 43, now=NOW + timedelta(minutes=1)
        )
    )["invalid"] == 1
    async with db.sessions() as session:
        assert await session.get(PushToken, "bob-phone") is None
        assert await session.get(PushOutbox, "bob-phone") is None


async def test_fcm_payload_has_no_conversation_content_or_identity():
    captured = []

    def handler(request):
        import json

        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"name": "projects/fixture/messages/1"})

    providers = PushProviders(
        settings(fcm_project_id="fixture"),
        transport=httpx.MockTransport(handler),
        credentials=SimpleNamespace(valid=True, token="fixture-credential"),
    )
    try:
        assert (
            await providers.send(
                SimpleNamespace(provider="fcm"),
                "fixture-device-token",
                NOW,
                NOW + timedelta(hours=72),
            )
            == "sent"
        )
        payload = captured[0]["message"]
        assert payload["data"] == {"kind": "inbox_changed"}
        assert "notification" not in payload and payload["android"]["ttl"] == "3600s"
    finally:
        await providers.close()


@pytest.mark.parametrize(
    "environment,host",
    [
        ("sandbox", "api.sandbox.push.apple.com"),
        ("production", "api.push.apple.com"),
    ],
)
async def test_apns_payload_matches_native_background_callback_fixture(
    tmp_path, environment, host
):
    key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "fixture-apns-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    expected = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "ios/VipiCryptoTests/APNsInboxChanged.json"
        ).read_text()
    )
    # The real server payload must resolve on every shipped Apple UI locale,
    # without learning the recipient's language or adding chat content to APNs.
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2] / "ios/Vipi/Localizable.xcstrings"
        ).read_text()
    )
    key = expected["aps"]["alert"]["loc-key"]
    localized = catalog["strings"][key]["localizations"]
    assert set(localized) == {
        "en",
        "ar",
        "de",
        "es",
        "fr",
        "it",
        "ja",
        "ko",
        "pt",
        "pt-PT",
        "sw",
        "zh-Hans",
        "zh-Hant",
    }
    assert all(value["stringUnit"]["value"].strip() for value in localized.values())
    assert set(expected["aps"]["alert"]) == {"title", "loc-key"}
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={})

    providers = PushProviders(
        settings(
            apns_private_key_path=str(key_path),
            apns_key_id="fixture-key-id",
            apns_sandbox_private_key_path=str(key_path),
            apns_sandbox_key_id="sandbox-fixture-key-id",
            apns_team_id="fixture-team",
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert (
            await providers.send(
                SimpleNamespace(provider="apns", environment=environment),
                "fixture-device-token",
                NOW,
                NOW + timedelta(hours=72),
            )
            == "sent"
        )
        assert len(requests) == 1
        request = requests[0]
        assert request.url.host == host
        assert request.headers["apns-topic"] == "co.fallsoft.vipi"
        assert request.headers["apns-push-type"] == "alert"
        assert request.headers["apns-expiration"] == str(int(NOW.timestamp()) + 3600)
        assert json.loads(request.content) == expected
    finally:
        await providers.close()


async def test_slow_provider_backoff_starts_at_completion_not_batch_start(db):
    await seed(db)
    current = NOW

    class SlowFailure:
        calls = 0

        async def send(self, registration, token, now, expires_at):
            nonlocal current
            self.calls += 1
            current += timedelta(seconds=90)
            return "retry"

    provider = SlowFailure()
    result = await process_pushes(
        db, provider, secret="a" * 43, now=NOW, clock=lambda: current
    )
    assert result["retry"] == 1 and provider.calls == 1
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.next_attempt_at.replace(tzinfo=NOW.tzinfo) == current + timedelta(
            seconds=30
        )
        assert job.lease_until is None


async def test_dispatch_deadline_leaves_unclaimed_notifications_for_next_pass(db):
    await seed(db)
    provider = Provider()
    result = await process_pushes(
        db, provider, secret="a" * 43, now=NOW, dispatch_seconds=0
    )
    assert not any(result.values()) and not provider.calls
    async with db.sessions() as session:
        job = await session.get(PushOutbox, "bob-phone")
        assert job.lease_token is None and job.attempts == 0


async def test_apns_credentials_are_separate_and_never_fall_back(tmp_path):
    import jwt

    production = ec.generate_private_key(ec.SECP256R1())
    sandbox = ec.generate_private_key(ec.SECP256R1())
    paths = []
    for name, key in (("production", production), ("sandbox", sandbox)):
        path = tmp_path / (name + ".pem")
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        paths.append(path)
    captured = []

    def handler(request):
        captured.append(request)
        return (
            httpx.Response(410, json={"reason": "Unregistered"})
            if len(captured) == 3
            else httpx.Response(200, json={})
        )

    config = settings(
        apns_private_key_path=str(paths[0]),
        apns_key_id="production-key",
        apns_sandbox_private_key_path=str(paths[1]),
        apns_sandbox_key_id="sandbox-key",
        apns_team_id="fixture-team",
    )
    providers = PushProviders(config, transport=httpx.MockTransport(handler))
    try:
        for environment, expected in (
            ("production", "sent"),
            ("sandbox", "sent"),
            ("production", "invalid"),
        ):
            assert (
                await providers.send(
                    SimpleNamespace(provider="apns", environment=environment),
                    "fixture-device-token",
                    NOW,
                    NOW + timedelta(hours=1),
                )
                == expected
            )
        assert [r.url.host for r in captured] == [
            "api.push.apple.com",
            "api.sandbox.push.apple.com",
            "api.push.apple.com",
        ]
        assert all(r.headers["apns-topic"] == "co.fallsoft.vipi" for r in captured)
        for request, key, expected_kid in zip(
            captured,
            (production, sandbox, production),
            ("production-key", "sandbox-key", "production-key"),
        ):
            token = request.headers["authorization"].split()[1]
            assert jwt.get_unverified_header(token)["kid"] == expected_kid
            assert (
                jwt.decode(
                    token,
                    key.public_key(),
                    algorithms=["ES256"],
                    options={"verify_iat": False},
                )["iss"]
                == "fixture-team"
            )
    finally:
        await providers.close()
    captured.clear()
    production_only = PushProviders(
        settings(
            apns_private_key_path=str(paths[0]),
            apns_key_id="production-key",
            apns_team_id="fixture-team",
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert (
            await production_only.send(
                SimpleNamespace(provider="apns", environment="sandbox"),
                "fixture-device-token",
                NOW,
                NOW + timedelta(hours=1),
            )
            == "retry"
        )
        assert (
            await production_only.send(
                SimpleNamespace(provider="apns", environment="invalid"),
                "fixture-device-token",
                NOW,
                NOW + timedelta(hours=1),
            )
            == "retry"
        )
        assert captured == []
    finally:
        await production_only.close()


@pytest.mark.parametrize(
    "sandbox",
    [
        {"apns_sandbox_key_id": "sandbox-id"},
        {"apns_sandbox_private_key_path": "/synthetic/key.pem"},
        {
            "apns_sandbox_key_id": "sandbox-id",
            "apns_sandbox_private_key_path": "/synthetic/key.pem",
        },
        {"apns_sandbox_key_id": "sandbox-id", "apns_team_id": "team"},
        {"apns_sandbox_private_key_path": "/synthetic/key.pem", "apns_team_id": "team"},
    ],
)
def test_apns_sandbox_partial_configuration_is_rejected(sandbox):
    with pytest.raises(
        ValueError, match="APNs sandbox requires key ID, private key path and team ID"
    ):
        settings(**sandbox)


def test_apns_sandbox_complete_configuration_is_accepted():
    configured = settings(
        apns_sandbox_key_id="sandbox-id",
        apns_sandbox_private_key_path="/synthetic/key.pem",
        apns_team_id="team",
    )
    assert configured.apns_sandbox_key_id == "sandbox-id"


async def test_preview_ticket_authenticates_one_device_and_ordered_ciphertexts(db):
    from dataclasses import replace
    from cryptography.fernet import InvalidToken
    from vipi.accounts import credential_hash
    from vipi.db import Block, Device, PendingMessage
    from vipi.delivery import DeliveryError
    from vipi.push import preview_envelope

    secret, proof = "s" * 43, "p" * 43
    async with db.sessions.begin() as session:
        phone = await session.get(Device, "bob-phone")
        phone.credential_hash = credential_hash(proof, secret)
        await register(
            session,
            user_id="bob",
            device_id=phone.id,
            provider="apns",
            environment="production",
            token="ab" * 32,
            secret=secret,
            now=NOW,
        )
        first = await accept(session, message(), now=NOW)
        second = await accept(
            session,
            replace(message(), created_at=NOW + timedelta(seconds=1)),
            now=NOW + timedelta(seconds=1),
        )
        await enqueue(session, phone.id, NOW, second.expires_at)
        first_id, second_id = first.id, second.id
    tickets = []

    class APNs:
        async def send(self, registration, token, now, expires_at, *, preview):
            tickets.append(preview)
            return "sent"

    assert (
        await process_pushes(db, APNs(), secret=secret, now=NOW + timedelta(seconds=2))
    )["sent"] == 1
    (ticket,) = tickets
    assert all(
        value not in ticket for value in (second_id, "bob-phone", "alice", proof)
    )
    with pytest.raises(InvalidToken):
        token_cipher(secret).decrypt(ticket.encode())
    async with db.sessions.begin() as session:
        params = dict(
            ticket=ticket,
            device_id="bob-phone",
            device_secret=proof,
            secret=secret,
            now=NOW + timedelta(seconds=2),
        )
        found = await preview_envelope(session, **params)
        assert found["id"] == second_id and found["peer"] == "alice"
        assert [item["id"] for item in found["messages"]] == [first_id, second_id]
        assert (await session.get(PendingMessage, first_id)).state == "accepted"
        assert (await session.get(PendingMessage, second_id)).state == "accepted"
        for changes in (
            {"device_secret": "x" * 43},
            {"device_id": "eve-phone"},
            {"now": NOW + timedelta(hours=2)},
        ):
            with pytest.raises(DeliveryError):
                await preview_envelope(session, **(params | changes))
        await acknowledge(
            session, second_id, "bob", "bob-phone", now=NOW + timedelta(seconds=3)
        )
        assert [
            item["id"]
            for item in (await preview_envelope(session, **params))["messages"]
        ] == [first_id]
        session.add(Block(blocker_id="bob", blocked_id="alice"))
        await session.flush()
        with pytest.raises(DeliveryError):
            await preview_envelope(session, **params)


def test_privacy_notice_describes_device_preview_settings():
    from vipi.public_pages import PAGES

    _, notice = PAGES["/privacy"]
    for wording in (
        "decrypts it locally",
        "Existing installations keep previous privacy choices",
        "banners inside Vipi have a separate setting",
        "generic alert",
    ):
        assert wording in notice


@pytest.mark.parametrize("kind", ["message", "control"])
async def test_group_bytes_stay_in_the_membership_aware_inbox(db, kind):
    from dataclasses import replace
    from vipi.accounts import credential_hash
    from vipi.db import Device
    from vipi.delivery import DeliveryError
    from vipi.push import preview_envelope, preview_ticket

    secret, proof = "s" * 43, "p" * 43
    async with db.sessions.begin() as session:
        phone = await session.get(Device, "bob-phone")
        phone.credential_hash = credential_hash(proof, secret)
        await register(
            session,
            user_id="bob",
            device_id=phone.id,
            provider="apns",
            environment="sandbox",
            token="ab" * 32,
            secret=secret,
            now=NOW,
        )
        group = await accept(session, message(), now=NOW)
        group.group_id, group.group_epoch, group.group_message_id, group.group_kind = (
            "g",
            1,
            "m",
            kind,
        )
        await enqueue(session, phone.id, NOW, group.expires_at)
        registration = await session.get(PushToken, phone.id)
        group_ticket = preview_ticket(secret, registration, group.id, NOW)
    # A group-only push remains a generic wakeup even without group-event coalescing.
    assert (await process_pushes(db, Provider(), secret=secret, now=NOW))["sent"] == 1
    async with db.sessions.begin() as session:
        later = NOW + timedelta(seconds=1)
        direct = await accept(session, replace(message(), created_at=later), now=later)
        registration = await session.get(PushToken, "bob-phone")
        direct_ticket = preview_ticket(secret, registration, direct.id, later)
        for ticket in (group_ticket, direct_ticket):
            with pytest.raises(DeliveryError, match="notification_unavailable"):
                await preview_envelope(
                    session,
                    ticket=ticket,
                    device_id="bob-phone",
                    device_secret=proof,
                    secret=secret,
                    now=later,
                )
        assert direct.state == "accepted"


async def test_retiring_worker_settles_an_expiring_push_and_leaves_new_work(db):
    await seed(db)
    boundary = NOW + timedelta(seconds=1)
    async with db.sessions.begin() as s:
        (await s.get(PushOutbox, "bob-phone")).expires_at = boundary
    entered, release, stopping = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class HeldProvider(Provider):
        async def send(self, *args, **kwargs):
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
            return await super().send(*args, **kwargs)

    original = HeldProvider()
    dispatch = asyncio.create_task(
        process_pushes(db, original, secret="a" * 43, now=NOW, stopping=stopping)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        stopping.set()
        other = Provider()
        await process_pushes(db, other, secret="a" * 43, now=boundary)
        async with db.sessions.begin() as s:
            row = await s.get(PushOutbox, "bob-phone")
            assert row is not None and row.lease_token and row.generation == 1
            await enqueue(s, "bob-phone", boundary, NOW + timedelta(hours=1))
    finally:
        release.set()
        result = await dispatch
    assert result["sent"] == 1 and result["lease_lost"] == 0
    assert len(original.calls) == 1 and not other.calls
    async with db.sessions() as s:
        row = await s.get(PushOutbox, "bob-phone")
        assert row.generation == 2 and row.lease_token is None
    assert (await process_pushes(db, other, secret="a" * 43, now=boundary))["sent"] == 1
    assert len(other.calls) == 1
