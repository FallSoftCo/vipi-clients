import asyncio
import base64
import hashlib
import json
import os
import time
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from conftest import NOW
from test_api import TestVerifier
from test_subscriptions import Provider, purchase, settings
from vipi.api import create_app
from vipi.db import BillingNotification, Entitlement
from vipi.delivery import DeliveryError
from vipi.store_notifications import PubSubVerifier, fingerprint, retain
from vipi.store_providers import AppleProvider
from vipi.subscriptions import Subscriptions


def google_settings(**kw):
    return settings(google_rtdn_audience="https://vipi.test/v1/store-notifications/google",
        google_rtdn_service_account="push@vipi-test.iam.gserviceaccount.com",
        google_rtdn_subscription="projects/vipi-test/subscriptions/billing", **kw)


@pytest.fixture
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="google-test", alg="RS256", use="sig")
    def token(**changes):
        claims = dict(iss="https://accounts.google.com", sub="123456789", iat=int(time.time()),
            exp=int(time.time()) + 3600, aud=google_settings().google_rtdn_audience,
            email=google_settings().google_rtdn_service_account, email_verified=True)
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid":"google-test"})
    return key, public, token


async def test_pubsub_verifies_signature_audience_issuer_account_and_expiry(signing):
    key, public, token = signing
    calls = []
    def respond(request):
        calls.append(request)
        assert str(request.url) == "https://www.googleapis.com/oauth2/v3/certs"
        return httpx.Response(200, json={"keys":[public]})
    verifier = PubSubVerifier(google_settings(), transport=httpx.MockTransport(respond))
    try:
        await verifier.verify(token())
        for change in ({"aud":"https://another.test"}, {"iss":"https://evil.test"},
                       {"email":"another@vipi-test.iam.gserviceaccount.com"},
                       {"email_verified":"true"}, {"email_verified":False},
                       {"exp":int(time.time())-20}, {"iat":int(time.time())+60},
                       {"exp":int(time.time())+7200}):
            with pytest.raises(DeliveryError, match="notification_unauthorized"):
                await verifier.verify(token(**change))
        forged = jwt.encode({"iat":int(time.time()), "exp":int(time.time())+100},
            rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256", headers={"kid":"google-test"})
        with pytest.raises(DeliveryError, match="notification_unauthorized"):
            await verifier.verify(forged)
        assert len(calls) == 1
    finally:
        await verifier.close()


async def test_authenticated_google_event_is_durable_idempotent_and_never_a_grant(db, signing):
    _, public, token = signing
    provider = Provider(purchase(transaction_id=hashlib.sha256(b"secret-token").hexdigest()))
    app = create_app(google_settings(), database=db, verifier=TestVerifier(), clock=lambda:NOW,
        store_providers={"google":provider}, notification_transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys":[public]})))
    service = app.state.subscriptions
    await service.apply("alice", provider.result, NOW)
    data = {"version":"1.0", "packageName":"co.fallsoft.vipi", "eventTimeMillis":str(int(NOW.timestamp()*1000)),
        "subscriptionNotification":{"version":"1.0", "notificationType":12, "purchaseToken":"secret-token"}}
    body = {"subscription":google_settings().google_rtdn_subscription,
        "message":{"messageId":"12345", "data":base64.b64encode(json.dumps(data).encode()).decode()}}
    headers = {"Authorization":"Bearer "+token()}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
            assert (await client.post("/v1/store-notifications/google", json=body)).status_code == 401
            for _ in range(2):
                reply = await client.post("/v1/store-notifications/google", json=body, headers=headers)
                assert reply.status_code == 204 and not reply.content
            async with db.sessions() as session:
                row = (await session.execute(select(Entitlement))).scalar_one()
                assert row.refresh_generation == 1 and row.completed_generation == 0
                assert row.next_attempt_at.replace(tzinfo=NOW.tzinfo) == NOW
                receipt = (await session.execute(select(BillingNotification))).scalar_one()
                assert receipt.id == "12345" and "secret-token" not in str(receipt.__dict__)
            assert provider.calls == 0
            assert (await service.snapshot("alice"))["base"]["active"]
            provider.result = replace(provider.result, revoked=True)
            assert await service.reconcile_one()
            assert not (await service.snapshot("alice"))["base"]["active"]
            assert provider.calls == 1
            # Same event ID with a different authenticated body cannot overwrite.
            data["subscriptionNotification"]["notificationType"] = 2
            body["message"]["data"] = base64.b64encode(json.dumps(data).encode()).decode()
            assert (await client.post("/v1/store-notifications/google", json=body, headers=headers)).status_code == 409
            body["subscription"] = "projects/another/subscriptions/billing"
            assert (await client.post("/v1/store-notifications/google", json=body, headers=headers)).status_code == 400
    finally:
        await app.state.pubsub_verifier.close(); await app.state.bot.close()


async def test_unknown_events_are_acknowledged_without_creating_entitlements(db):
    await retain(db, store="google", event_id="unknown", digest=fingerprint({"unknown":True}),
        transaction_id="not-a-purchase", now=NOW)
    async with db.sessions() as session:
        assert (await session.execute(select(Entitlement))).scalars().all() == []


async def test_reconciliation_backoff_preserves_access_but_not_past_expiry(db):
    class Offline(Provider):
        async def verify(self, *args, **kwargs):
            self.calls += 1
            raise DeliveryError("purchase_verification_unavailable", 503)
    provider = Offline(purchase())
    clock = [NOW]
    service = Subscriptions(settings(), db, {"google":provider}, lambda:clock[0])
    await service.apply("alice", purchase(), NOW)
    clock[0] += timedelta(minutes=6)
    for _ in range(20):
        assert (await service.snapshot("alice"))["base"]["active"]
    assert provider.calls == 0
    assert await service.reconcile_one()
    assert not await service.reconcile_one()
    assert provider.calls == 1
    assert (await service.snapshot("alice"))["base"]["active"]
    await service.apply("alice", purchase(expires_at=clock[0]+timedelta(seconds=1)), clock[0])
    clock[0] += timedelta(seconds=2)
    assert not (await service.snapshot("alice"))["base"]["active"]


async def test_old_expired_reference_does_not_remain_a_permanent_job(db):
    class Expired(Provider):
        async def verify(self, *args, **kwargs):
            self.calls += 1
            raise DeliveryError("purchase_invalid", 400)
    provider = Expired(purchase())
    clock = [NOW]
    service = Subscriptions(settings(), db, {"google":provider}, lambda:clock[0])
    await service.apply("alice", purchase(expires_at=NOW-timedelta(days=61)), NOW)
    await retain(db, store="google", event_id="very-late", digest="1"*64,
        transaction_id="transaction-one", now=NOW)
    assert await service.reconcile_one()
    clock[0] += timedelta(days=2)
    assert not await service.reconcile_one()
    assert not (await service.snapshot("alice"))["base"]["active"]


@pytest.mark.skipif(not os.environ.get("VIPI_TEST_POSTGRES_URL"), reason="actual PostgreSQL row locking")
async def test_concurrent_reconcile_and_new_event_preserve_new_generation(db):
    started, finish = asyncio.Event(), asyncio.Event()
    class Waiting(Provider):
        async def verify(self, *args, **kwargs):
            self.calls += 1; started.set(); await finish.wait()
            return self.result
    provider = Waiting(purchase())
    service = Subscriptions(settings(), db, {"google":provider}, lambda:NOW)
    await service.apply("alice", purchase(), NOW)
    await retain(db, store="google", event_id="first", digest="1"*64, transaction_id="transaction-one", now=NOW)
    job = asyncio.create_task(service.reconcile_one())
    await asyncio.wait_for(started.wait(), 5)
    try:
        assert not await service.reconcile_one()
        await retain(db, store="google", event_id="second", digest="2"*64, transaction_id="transaction-one", now=NOW)
    finally:
        finish.set(); await job
    async with db.sessions() as session:
        row = (await session.execute(select(Entitlement))).scalar_one()
        assert row.refresh_generation == 2 and row.completed_generation == 1
    assert await service.reconcile_one()
    assert provider.calls == 2


async def test_apple_notification_uses_official_signed_verifier_and_current_status(db):
    provider = AppleProvider.__new__(AppleProvider)
    provider.parallel = asyncio.Semaphore(1)
    event_id = str(uuid4())
    def verified(signed):
        assert signed == "signed-test-notification"
        return SimpleNamespace(version="2.0", notificationUUID=event_id,
            data=SimpleNamespace(signedTransactionInfo="signed-test-transaction"),
            rawNotificationType="REFUND", rawSubtype=None, signedDate=int(NOW.timestamp()*1000))
    async def decoded(signed):
        assert signed == "signed-test-transaction"
        return SimpleNamespace(productId="vipi.base.annual", originalTransactionId="123456")
    provider.verifier = SimpleNamespace(verify_and_decode_notification=verified)
    provider.decode = decoded
    app = create_app(settings(), database=db, verifier=TestVerifier(), clock=lambda:NOW, store_providers={"apple":provider})
    try:
        await app.state.subscriptions.apply("alice", purchase(store="apple", transaction_id="123456"), NOW)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
            for _ in range(2):
                assert (await client.post("/v1/store-notifications/apple", json={"signedPayload":"signed-test-notification"})).status_code == 204
        async with db.sessions() as session:
            row = (await session.execute(select(Entitlement))).scalar_one()
            assert row.refresh_generation == 1 and not row.revoked  # event itself cannot grant/revoke
        from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus
        def bad(_): raise VerificationException(VerificationStatus.INVALID_ENVIRONMENT)
        provider.verifier = SimpleNamespace(verify_and_decode_notification=bad)
        with pytest.raises(DeliveryError, match="notification_invalid"):
            await provider.notification("wrong-app-or-environment")
    finally:
        await app.state.pubsub_verifier.close(); await app.state.bot.close()
