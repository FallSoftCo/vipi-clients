import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from test_identity_linking import LegacyVerifier, SharedVerifier, SECRET, settings
from test_api import identity
from vipi.api import create_app
from vipi.db import (
    IdentityAuthorityAlias,
    GlobalDeletionHold,
    GlobalDeletionReceipt,
    User,
    VipiTrialEligibility,
    VipiTrialEligibilityLink,
)
from vipi.delivery import DeliveryError
from vipi.eligibility import eligibility_hash, original_trial
from vipi.global_deletion import CONTRACT, PATH, erase, expire_receipts
from vipi.identity_authorities import canonical_shared_subject

KEY = "global-deletion-test-fixture-" * 3


def operation(**changes):
    return {
        "requestId": str(uuid4()),
        "subject": "user_shared_alice",
        "scope": "fallsoft",
        "subjectHash": "a" * 64,
        "consentVersion": "fallsoft-account-deletion-1",
        "contractVersion": CONTRACT,
    } | changes


def signed(value, action="erase", now=NOW, key=KEY):
    raw = json.dumps(value).encode()
    at, nonce = str(int(now.timestamp())), secrets.token_urlsafe(24)
    digest = hashlib.sha256(raw).hexdigest()
    signature = hmac.new(
        key.encode(),
        "\n".join(
            (
                "fallsoft-account-deletion-v1",
                "vipi",
                "POST",
                PATH + "/" + action,
                at,
                nonce,
                digest,
            )
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "content": raw,
        "headers": {
            "Content-Type": "application/json",
            "X-Fallsoft-Deletion-Time": at,
            "X-Fallsoft-Deletion-Nonce": nonce,
            "X-Fallsoft-Deletion-Signature": signature,
        },
    }


def client(db, enabled=True):
    app = create_app(
        settings(global_deletion_enabled=enabled, global_deletion_secret=KEY),
        database=db,
        verifier=LegacyVerifier(),
        shared_verifier=SharedVerifier(),
        clock=lambda: NOW,
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    )


async def test_global_erasure_atomic_receipt_retry_and_legacy_alias_hold(db):
    value = operation()
    async with client(db) as api:
        profile, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": profile["id"],
            "fallsoft_access_token": "shared-alice",
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).status_code == 200
        before = await api.post(PATH + "/status", **signed(value, "status"))
        assert before.json()["status"] == "not_started"
        response = await api.post(PATH + "/erase", **signed(value))
        assert response.status_code == 200, response.text
        assert (
            response.json()["status"] == "complete"
            and response.json()["reprovisionBlocked"]
        )
        assert (
            await api.post(PATH + "/erase", **signed(value))
        ).json() == response.json()
        assert (
            await api.post(PATH + "/status", **signed(value, "status"))
        ).json() == response.json()
        for token in ("alice", "shared-alice"):
            assert (
                await api.put(
                    "/v1/me",
                    headers={"Authorization": "Bearer " + token},
                    json={"username": "recreated", "display_name": "Wrong"},
                )
            ).json() == {"error": "account_deleted"}
    async with db.sessions() as session:
        assert await session.get(User, profile["id"]) is None
        assert await session.get(User, "bob") is not None
        assert len((await session.scalars(select(GlobalDeletionHold))).all()) == 2
        assert not (await session.scalars(select(VipiTrialEligibility))).all()
        assert not (await session.scalars(select(VipiTrialEligibilityLink))).all()
        assert not (await session.scalars(select(IdentityAuthorityAlias))).all()
        receipt = await session.get(GlobalDeletionReceipt, value["requestId"])
        assert receipt.subject_hash != value["subject"]


@pytest.mark.parametrize(
    "kind",
    [
        "wrong-key",
        "stale",
        "modified-body",
        "wrong-path",
        "wrong-scope",
        "duplicate-json",
    ],
)
async def test_invalid_signed_deletion_cannot_mutate(db, kind):
    value = operation()
    arguments = signed(value)
    if kind == "wrong-key":
        arguments = signed(value, key="x" * 64)
    if kind == "stale":
        arguments = signed(value, now=NOW - timedelta(seconds=61))
    if kind == "modified-body":
        arguments["content"] = arguments["content"].replace(b"alice", b"eve")
    if kind == "wrong-path":
        arguments = signed(value, "status")
    if kind == "wrong-scope":
        arguments = signed(value | {"scope": "vipi"})
    if kind == "duplicate-json":
        # Authenticated but ambiguous JSON is also rejected.
        from vipi.global_deletion import verify_operation

        raw = arguments["content"][:-1] + b',"scope":"fallsoft"}'
        hdr = arguments["headers"]
        signing = "\n".join(
            (
                "fallsoft-account-deletion-v1",
                "vipi",
                "POST",
                PATH + "/erase",
                hdr["X-Fallsoft-Deletion-Time"],
                hdr["X-Fallsoft-Deletion-Nonce"],
                hashlib.sha256(raw).hexdigest(),
            )
        )
        hdr["X-Fallsoft-Deletion-Signature"] = hmac.new(
            KEY.encode(), signing.encode(), hashlib.sha256
        ).hexdigest()
        arguments["content"] = raw
    async with client(db) as api:
        response = await api.post(PATH + "/erase", **arguments)
        assert response.status_code in (400, 401)
    async with db.sessions() as session:
        assert not (await session.scalars(select(GlobalDeletionHold))).all()
        assert not (await session.scalars(select(GlobalDeletionReceipt))).all()


async def test_adapter_is_absent_until_explicitly_enabled(db):
    async with client(db, enabled=False) as api:
        assert (
            await api.post(PATH + "/erase", **signed(operation()))
        ).status_code == 404


async def test_no_profile_erasure_removes_original_trial_and_keeps_unrelated_record(db):
    subject = canonical_shared_subject("user_shared_alice")
    async with db.sessions.begin() as session:
        await original_trial(
            session, subject=subject, service_secret=SECRET, started_at=NOW
        )
        await original_trial(
            session, subject="user_unrelated", service_secret=SECRET, started_at=NOW
        )
    value = operation()
    async with client(db) as api:
        assert (await api.post(PATH + "/erase", **signed(value))).status_code == 200
        conflict = await api.post(
            PATH + "/erase", **signed(value | {"subject": "user_shared_eve"})
        )
        assert conflict.status_code == 409
    async with db.sessions() as session:
        assert [
            r.subject_hash
            for r in (await session.scalars(select(VipiTrialEligibility))).all()
        ] == [eligibility_hash("user_unrelated", SECRET)]


async def test_rollback_does_not_leave_success_receipt_or_hold(db):
    value = operation()
    with pytest.raises(RuntimeError, match="rollback"):
        async with db.sessions.begin() as session:
            await erase(session, value, SECRET, NOW)
            raise RuntimeError("rollback")
    async with db.sessions() as session:
        assert await session.get(GlobalDeletionReceipt, value["requestId"]) is None
        assert (
            await session.get(
                GlobalDeletionHold,
                eligibility_hash(canonical_shared_subject(value["subject"]), SECRET),
            )
            is None
        )


async def test_receipt_expiry_never_removes_reprovision_hold(db):
    value = operation()
    async with db.sessions.begin() as session:
        await erase(session, value, SECRET, NOW)
    async with db.sessions.begin() as session:
        await expire_receipts(session, NOW + timedelta(days=8))
    async with db.sessions() as session:
        assert await session.get(GlobalDeletionReceipt, value["requestId"]) is None
        assert (
            await session.get(
                GlobalDeletionHold,
                eligibility_hash(canonical_shared_subject(value["subject"]), SECRET),
            )
            is not None
        )


async def test_hold_blocks_access_even_if_a_profile_is_restored(db):
    # A database restored outside the required quarantine must still not reopen
    # access to an identity for which the durable erasure hold was retained.
    value = operation()
    async with db.sessions.begin() as session:
        await erase(session, value, SECRET, NOW)
        session.add(
            User(
                id=str(uuid4()),
                subject=canonical_shared_subject(value["subject"]),
                username="restored_wrongly",
                display_name="Held",
                created_at=NOW,
            )
        )
    async with client(db) as api:
        response = await api.get(
            "/v1/me", headers={"Authorization": "Bearer shared-alice"}
        )
        assert response.status_code == 403 and response.json() == {
            "error": "account_deleted"
        }


async def test_concurrent_exact_global_retry_one_receipt(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires real PostgreSQL advisory locking")
    import asyncio

    value = operation()

    async def apply():
        async with db.sessions.begin() as session:
            return await erase(session, value, SECRET, NOW)

    first, second = await asyncio.gather(apply(), apply())
    assert first == second and first["status"] == "complete"
