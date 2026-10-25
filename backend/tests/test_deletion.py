from datetime import timedelta
import secrets
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_api import TestVerifier, identity
from test_delivery import message
from vipi.api import create_app
from vipi.auth import Principal
from vipi.config import Settings
from vipi.db import AccountDeletion, Block, Device, Entitlement, KeyClaim, PendingMessage, PublicBundle, PublicPreKey, RateWindow, Reservation, UsageBucket, User
from vipi.deletion import WorkOSUserDeleter, deletion_status, expire_deletion_receipts, process_deletions, request_deletion
from vipi.delivery import DeliveryError, accept, utc

KEY = "deletion-test-" * 4


def settings(**extra):
    return Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com", service_secret=KEY, account_deletion_enabled=True,
        workos_dedicated_user_pool=True, workos_api_key="test-key-never-live", **extra)


async def erase(db, secret, who="alice"):
    async with db.sessions.begin() as session:
        return await request_deletion(session, subject="user_"+who, account_id=who,
                                      receipt_secret=secret, service_secret=KEY, now=NOW)


async def test_deletion_removes_related_records_and_preserves_other_accounts(db):
    secret = secrets.token_urlsafe(32)
    async with db.sessions.begin() as s:
        await accept(s, message(), now=NOW)
        for user in ("alice", "bob"):
            s.add(PublicBundle(device_id=user+"-phone", registration_id=1, identity_key=b"public fixture", signed_key_id=1,
                signed_key=b"key", signed_signature=b"signature", revision=1, fingerprint="f"*64, high_key_id=1))
            s.add(PublicPreKey(device_id=user+"-phone", key_id=1, ec_key=b"ec", kem_key=b"kem", kem_signature=b"signature"))
        s.add_all([
            KeyClaim(requester_device_id="alice-phone", id="claim-from-alice", recipient_id="bob", recipient_device_id="bob-phone", created_at=NOW, response=b"public bundle"),
            KeyClaim(requester_device_id="bob-phone", id="claim-for-alice", recipient_id="alice", recipient_device_id="alice-phone", created_at=NOW, response=b"public bundle"),
            KeyClaim(requester_device_id="bob-phone", id="claim-for-eve", recipient_id="eve", recipient_device_id="eve-phone", created_at=NOW, response=b"unrelated"),
            Block(blocker_id="alice", blocked_id="bob"), Block(blocker_id="bob", blocked_id="alice"), Block(blocker_id="bob", blocked_id="eve"),
            Entitlement(id="purchase", user_id="alice", product="base", store="test", transaction_id="test-transaction", expires_at=NOW+timedelta(days=1)),
            Reservation(id="reservation", user_id="alice", period="2026-10", reserved_nano_usd=100, created_at=NOW),
            RateWindow(subject="user_alice", scope="test", window=1, count=1),
        ])
    await erase(db, secret)
    async with db.sessions() as s:
        assert await s.get(User, "alice") is None
        assert await s.get(Device, "alice-phone") is None
        assert await s.get(User, "bob") and await s.get(Device, "bob-phone")
        for model in (PendingMessage, Entitlement, Reservation, UsageBucket, RateWindow):
            assert (await s.scalar(select(func.count()).select_from(model))) == 0
        assert await s.get(PublicBundle, "alice-phone") is None
        assert await s.get(PublicPreKey, ("alice-phone", 1)) is None
        assert await s.get(PublicBundle, "bob-phone") is not None
        assert (await s.scalars(select(KeyClaim.id))).all() == ["claim-for-eve"]
        blocks = (await s.scalars(select(Block))).all()
        assert [(b.blocker_id, b.blocked_id) for b in blocks] == [("bob", "eve")]
        receipt = await s.get(AccountDeletion, "alice")
        assert receipt.subject == "user_alice" and receipt.receipt_hash != secret and receipt.finished_at is None
    # Response-loss retries neither recreate an account nor touch the peer.
    await erase(db, secret)
    with pytest.raises(DeliveryError, match="deletion_receipt_unavailable"):
        await erase(db, secrets.token_urlsafe(32))


async def test_deletion_transaction_rolls_back_all_effects(db):
    with pytest.raises(RuntimeError, match="simulated failure"):
        async with db.sessions.begin() as s:
            await request_deletion(s, subject="user_alice", account_id="alice", receipt_secret=secrets.token_urlsafe(32), service_secret=KEY, now=NOW)
            raise RuntimeError("simulated failure")
    async with db.sessions() as s:
        assert await s.get(User, "alice") and await s.get(Device, "alice-phone")
        assert await s.get(UsageBucket, ("alice", "2026-10"))
        assert await s.get(AccountDeletion, "alice") is None


async def test_identity_cleanup_retries_and_receipt_survives_removed_sign_in(db):
    secret = secrets.token_urlsafe(32)
    await erase(db, secret)
    calls = []
    responses = [503, 404]
    async def upstream(request):
        assert request.method == "DELETE" and str(request.url) == "https://api.workos.com/user_management/users/user_alice"
        assert request.headers["Authorization"] == "Bearer test-key-never-live"
        calls.append(request)
        return httpx.Response(responses.pop(0), text="provider body must not be stored")
    deleter = WorkOSUserDeleter(settings(), transport=httpx.MockTransport(upstream))
    try:
        assert (await process_deletions(db, deleter, now=NOW))["retry"] == 1
        assert (await process_deletions(db, deleter, now=NOW+timedelta(seconds=20)))["finished"] == 0
        assert len(calls) == 1
        async with db.sessions() as s:
            receipt = await s.get(AccountDeletion, "alice")
            assert receipt.error_code == "identity_cleanup_unavailable" and receipt.subject == "user_alice"
        assert (await process_deletions(db, deleter, now=NOW+timedelta(seconds=31)))["finished"] == 1
        async with db.sessions() as s:
            receipt = await s.get(AccountDeletion, "alice")
            assert receipt.subject is None and receipt.error_code is None and receipt.finished_at is not None
            assert await deletion_status(s, account_id="alice", receipt_secret=secret, service_secret=KEY) == {"account_id":"alice", "status":"deleted"}
            with pytest.raises(DeliveryError):
                await deletion_status(s, account_id="alice", receipt_secret=secrets.token_urlsafe(32), service_secret=KEY)
    finally:
        await deleter.close()


async def test_expired_worker_lease_recovery_and_bounded_receipt_retention(db):
    await erase(db, secrets.token_urlsafe(32))
    await erase(db, secrets.token_urlsafe(32), "bob")
    async with db.sessions.begin() as s:
        job = await s.get(AccountDeletion, "alice")
        job.lease_token = "lost-worker"; job.lease_until = NOW+timedelta(minutes=2)
        other = await s.get(AccountDeletion, "bob")
        other.next_attempt_at = NOW+timedelta(days=20)
    class Provider:
        async def delete(self, subject): assert subject == "user_alice"
    assert (await process_deletions(db, Provider(), now=NOW))["finished"] == 0
    assert (await process_deletions(db, Provider(), now=NOW+timedelta(minutes=3)))["finished"] == 1
    async with db.sessions.begin() as s:
        await expire_deletion_receipts(s, NOW+timedelta(days=8))
    async with db.sessions() as s:
        assert await s.get(AccountDeletion, "alice") is None
        assert (await s.get(AccountDeletion, "bob")).subject == "user_bob"


async def test_account_deletion_api_requires_recent_identity_and_resumes_without_it(db):
    class Verifier(TestVerifier):
        async def verify(self, token):
            if token == "stale-alice": return Principal("user_qa_alice", "stale", int(NOW.timestamp())-601)
            return await super().verify(token)
    app = create_app(settings(), database=db, verifier=Verifier(), clock=lambda:NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as api:
        alice, _, headers = await identity(api, "alice")
        bob, _, bob_headers = await identity(api, "bob")
        body = {"account_id": alice["id"], "receipt_secret": secrets.token_urlsafe(32)}
        assert (await api.request("DELETE", "/v1/me", json=body)).status_code == 401
        assert (await api.request("DELETE", "/v1/me", json=body, headers={"Authorization":"Bearer stale-alice"})).status_code == 401
        assert (await api.request("DELETE", "/v1/me", json=body|{"account_id":bob["id"]}, headers=headers)).status_code == 409
        assert (await api.get("/v1/me", headers=headers)).json() == alice
        response = await api.request("DELETE", "/v1/me", json=body, headers=headers)
        assert response.status_code == 202 and response.json()["status"] == "deletion_requested"
        assert (await api.request("DELETE", "/v1/me", json=body, headers=headers)).json() == response.json()
        assert (await api.get("/v1/me", headers=headers)).status_code == 404
        assert (await api.get("/v1/messages/pending", headers=headers)).status_code == 404
        assert (await api.get("/v1/people/qa_alice", headers=bob_headers)).status_code == 404
        assert (await api.put("/v1/me", headers=headers, json={"username":"new_alice", "display_name":"New"})).status_code == 409
        url = "/v1/account-deletions/"+alice["id"]
        assert (await api.get(url, headers=headers)).status_code == 404
        assert (await api.get(url, headers={"Authorization":"Deletion "+secrets.token_urlsafe(32)})).status_code == 404
        capability = {"Authorization":"Deletion "+body["receipt_secret"]}
        assert (await api.get(url, headers=capability)).json() == response.json()
        assert (await api.get("/v1/account-deletions/"+bob["id"], headers=capability)).status_code == 404
        assert (await api.get("/v1/me", headers=bob_headers)).json() == bob


def test_shared_identity_pool_cannot_enable_provider_deletion():
    with pytest.raises(ValueError, match="dedicated Vipi identity pool"):
        Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture", workos_issuer="https://api.workos.com",
                 service_secret=KEY, account_deletion_enabled=True, workos_api_key="not-a-live-secret")


async def test_deletion_is_available_before_username_setup_without_touching_other_users(db):
    app = create_app(settings(), database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as api:
        headers = {"Authorization": "Bearer alice"}
        body = {"account_id": str(uuid4()), "receipt_secret": secrets.token_urlsafe(32)}
        assert (await api.get("/v1/me", headers=headers)).status_code == 404
        response = await api.request("DELETE", "/v1/me", json=body, headers=headers)
        assert response.status_code == 202
        assert (await api.request("DELETE", "/v1/me", json=body, headers=headers)).json() == response.json()
        assert (await api.put("/v1/me", json={"username": "qa_alice", "display_name": "QA"}, headers=headers)).status_code == 409
    async with db.sessions() as s:
        assert all([await s.get(User, name) is not None for name in ("alice", "bob", "eve")])
    with pytest.raises(DeliveryError, match="account_changed"):
        async with db.sessions.begin() as s:
            await request_deletion(s, subject="user_new", account_id="bob", receipt_secret=secrets.token_urlsafe(32), service_secret=KEY, now=NOW)
