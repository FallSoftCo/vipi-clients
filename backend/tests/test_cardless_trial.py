from datetime import timedelta
import pytest
from sqlalchemy import update
from conftest import NOW
from vipi.db import User
from vipi.delivery import DeliveryError
from vipi.subscriptions import Subscriptions
from test_subscriptions import settings, purchase
from test_api import api


async def set_trial(db, start, end):
    async with db.sessions.begin() as session:
        await session.execute(
            update(User)
            .where(User.id == "alice")
            .values(cardless_trial_started_at=start, cardless_trial_ends_at=end)
        )


async def test_trial_boundaries_reinstall_and_bot_separation(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    clock = [NOW]
    service = Subscriptions(settings(), db, {}, lambda: clock[0])
    first = await service.snapshot("alice")
    assert (
        first["base"]["active"] and first["base"]["access_source"] == "cardless_trial"
    )
    assert (
        first["base"]["cardless_trial"]["active"] and not first["bot_mini"]["available"]
    )
    with pytest.raises(DeliveryError, match="bot_subscription_required"):
        await service.require("alice", bot=True)
    # A fresh service instance, as after device replacement, cannot restart time.
    assert (
        await Subscriptions(settings(), db, {}, lambda: clock[0]).snapshot("alice")
    )["base"]["cardless_trial"] == first["base"]["cardless_trial"]
    clock[0] += timedelta(days=30) - timedelta(microseconds=1)
    assert (await service.snapshot("alice"))["base"]["active"]
    clock[0] += timedelta(microseconds=1)
    expired = await service.snapshot("alice")
    assert not expired["base"]["active"] and expired["base"]["access_source"] is None
    assert (
        not expired["base"]["cardless_trial"]["active"]
        and expired["base"]["cardless_trial"]["ends_at"]
        == first["base"]["cardless_trial"]["ends_at"]
    )
    with pytest.raises(DeliveryError, match="base_subscription_required"):
        await service.require("alice")


async def test_store_precedes_trial_then_trial_survives_revocation(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    service = Subscriptions(settings(), db, {}, lambda: NOW)
    await service.apply("alice", purchase(), NOW)
    assert (await service.snapshot("alice"))["base"]["access_source"] == "store"
    await service.apply("alice", purchase(revoked=True), NOW + timedelta(seconds=1))
    state = await service.snapshot("alice")
    assert (
        state["base"]["access_source"] == "cardless_trial"
        and state["base"]["cardless_trial"]["active"]
    )


async def test_registering_same_profile_does_not_start_a_trial(api, db):
    headers = {"Authorization": "Bearer alice"}
    profile = {"username": "qa_alice", "display_name": "Alice"}
    first = await api.put("/v1/me", json=profile, headers=headers)
    assert first.status_code == 200
    repeated = await api.put("/v1/me", json=profile, headers=headers)
    assert repeated.json() == first.json()
    async with db.sessions() as session:
        user = await session.get(User, first.json()["id"])
        assert (
            user.cardless_trial_started_at
            == user.cardless_trial_ends_at
            == user.created_at
        )
    state = (await api.get("/v1/entitlements", headers=headers)).json()
    assert (
        state["base"]["access_source"] == "free"
        and state["base"]["trial_ends_at"] is None
    )


async def test_review_complimentary_keeps_its_source_and_trial_is_not_bot(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    service = Subscriptions(
        settings(reviewer_user_ids={"11111111-1111-4111-8111-111111111111"}),
        db,
        {},
        lambda: NOW,
    )
    # A non-reviewer remains a trial user; reviewer matching is exact internal UUID.
    result = await service.snapshot("alice")
    assert (
        result["base"]["access_source"] == "cardless_trial"
        and not result["bot_mini"]["available"]
    )


async def test_deletion_removes_trial_and_blocks_same_subject_during_deletion(db):
    from vipi.deletion import request_deletion, deletion_for

    await set_trial(db, NOW, NOW + timedelta(days=30))
    async with db.sessions.begin() as session:
        await request_deletion(
            session,
            subject="user_alice",
            account_id="alice",
            receipt_secret="a" * 43,
            service_secret="a" * 43,
            now=NOW,
        )
    async with db.sessions() as session:
        assert await session.get(User, "alice") is None
        assert await deletion_for(session, "user_alice", "a" * 43) is not None
    with pytest.raises(DeliveryError, match="account_unavailable"):
        await Subscriptions(settings(), db, {}, lambda: NOW).snapshot("alice")


async def test_unapproved_sandbox_grant_cannot_supplant_cardless_trial(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    service = Subscriptions(
        settings(store_sandbox_restricted=True), db, {}, lambda: NOW
    )
    with pytest.raises(DeliveryError, match="purchase_environment_mismatch"):
        await service.apply("alice", purchase(), NOW)
    state = await service.snapshot("alice")
    assert state["base"]["access_source"] == "cardless_trial"
    assert state["base"]["active"] and not state["bot_mini"]["active"]


@pytest.mark.parametrize(
    "account_state", ["new", "expired_trial", "existing_subscriber"]
)
async def test_free_profiles_exchange_encrypted_envelopes_and_report(db, account_state):
    import base64
    import secrets
    from uuid import uuid4

    import httpx
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from sqlalchemy import select

    from test_api import TestVerifier, identity
    from vipi.api import create_app
    from vipi.db import Entitlement

    options = settings(enforce_subscriptions=True)
    app = create_app(
        options,
        database=db,
        verifier=TestVerifier(),
        clock=lambda: NOW,
        store_providers={},
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
        ) as client:
            alice = await identity(client, "alice")
            bob = await identity(client, "bob")
            if account_state == "expired_trial":
                async with db.sessions.begin() as session:
                    user = await session.get(User, alice[0]["id"])
                    user.cardless_trial_started_at = NOW - timedelta(days=65)
                    user.cardless_trial_ends_at = NOW - timedelta(days=35)
            elif account_state == "existing_subscriber":
                for product in ("base", "bot_mini"):
                    await app.state.subscriptions.apply(
                        alice[0]["id"], purchase(product, transaction_id=product), NOW
                    )
            state = (await client.get("/v1/entitlements", headers=alice[2])).json()
            assert state["base"]["active"] and state["base"]["access_source"] == "free"
            assert state["bot_mini"]["available"] is (
                account_state == "existing_subscriber"
            )
            assert not any(state["purchases_ready"].values())

            # The relay transports opaque bytes. Client-side AEAD exercises actual
            # ciphertext integrity independently of the native Signal protocol.
            cipher = AESGCM(AESGCM.generate_key(bit_length=256))
            for sender, recipient in ((alice, bob), (bob, alice)):
                plaintext = f"Private synthetic message for {recipient[0]['username']}"
                nonce = secrets.token_bytes(12)
                ciphertext = nonce + cipher.encrypt(nonce, plaintext.encode(), None)
                body = {
                    "id": str(uuid4()),
                    "recipient_id": recipient[0]["id"],
                    "recipient_device_id": recipient[1],
                    "created_at": NOW.isoformat(),
                    "cipher_type": 3,
                    "ciphertext": base64.b64encode(ciphertext).decode(),
                }
                sent = await client.post("/v1/messages", json=body, headers=sender[2])
                assert sent.status_code == 200 and sent.json()["state"] == "accepted"
                inbox = await client.get("/v1/messages/pending", headers=recipient[2])
                assert inbox.status_code == 200 and plaintext not in inbox.text
                (received,) = inbox.json()["messages"]
                assert (
                    received["id"] == body["id"]
                    and received["sender_id"] == sender[0]["id"]
                )
                payload = base64.b64decode(received["ciphertext"], validate=True)
                selected = cipher.decrypt(payload[:12], payload[12:], None).decode()
                assert selected == plaintext
                report = await client.post(
                    "/v1/reports",
                    headers=recipient[2],
                    json={
                        "report_id": str(uuid4()),
                        "reported_user_id": sender[0]["id"],
                        "message_id": body["id"],
                        "reason": "other",
                        "selected_text": selected,
                        "consent_version": "report-v1",
                    },
                )
                assert report.status_code == 202 and report.json()["reported"]
                ack = await client.post(
                    "/v1/messages/" + body["id"] + "/receipt", headers=recipient[2]
                )
                assert ack.status_code == 200 and ack.json()["state"] == "delivered"
            async with db.sessions() as session:
                rows = (await session.scalars(select(Entitlement))).all()
                if account_state == "existing_subscriber":
                    assert {(row.product, row.transaction_id) for row in rows} == {
                        ("base", "base"),
                        ("bot_mini", "bot_mini"),
                    }
                    assert all(
                        row.user_id == alice[0]["id"] and not row.revoked
                        for row in rows
                    )
                else:
                    assert not rows
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()


async def test_trial_keeps_base_available_during_stale_bot_verification(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    clock = [NOW]
    service = Subscriptions(
        settings(purchase_outage_seconds=300), db, {}, lambda: clock[0]
    )
    await service.apply("alice", purchase(product="bot_mini"), NOW)
    clock[0] += timedelta(seconds=301)
    state = await service.snapshot("alice")
    assert (
        state["base"]["active"] and state["base"]["access_source"] == "cardless_trial"
    )
    assert (
        not state["bot_mini"]["active"]
        and state["bot_mini"]["verification_unavailable"] is True
    )
    assert (await service.require("alice"))["base"]["active"]
    with pytest.raises(DeliveryError, match="purchase_verification_unavailable"):
        await service.require("alice", bot=True)
