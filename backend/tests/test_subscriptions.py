from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import Entitlement
from vipi.delivery import DeliveryError
from vipi.store_providers import GoogleProvider, AppleProvider
from vipi.subscriptions import Subscriptions, VerifiedPurchase, billing_account_id
from test_api import TestVerifier, identity


def settings(**kwargs):
    return Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com", service_secret="a" * 43, **kwargs)


def purchase(product="base", **kwargs):
    return replace(VerifiedPurchase("google", "secret-token", "transaction-one", product,
        NOW + timedelta(days=31), False, "Sandbox", NOW + timedelta(days=31)), **kwargs)


class Provider:
    def __init__(self, result):
        self.result, self.calls, self.ack = result, 0, 0
    async def verify(self, credential, user_id, *, initial):
        self.calls += 1
        return self.result
    async def acknowledge(self, result):
        self.ack += 1


async def test_provider_authority_trial_restore_and_expiry(db):
    provider = Provider(purchase())
    clock = [NOW]
    service = Subscriptions(settings(), db, {"google": provider}, lambda: clock[0])
    assert not (await service.snapshot("alice"))["base"]["active"]
    result = await service.sync("alice", "google", "untrusted-client-input")
    assert result["base"]["active"] and result["base"]["trial_ends_at"]
    assert not result["bot_mini"]["available"]
    assert result["billing_account_id"] == billing_account_id("alice")
    await service.sync("alice", "google", "same-transaction")
    async with db.sessions() as session:
        rows = (await session.execute(select(Entitlement).where(Entitlement.user_id == "alice"))).scalars().all()
        assert len(rows) == 1 and b"secret-token" not in rows[0].provider_reference
    provider.result = replace(provider.result, expires_at=NOW + timedelta(days=365), trial_ends_at=None)
    clock[0] += timedelta(minutes=6)
    assert (await service.snapshot("alice"))["base"]["trial_ends_at"] is None
    provider.result = replace(provider.result, revoked=True)
    clock[0] += timedelta(minutes=6)
    assert not (await service.snapshot("alice"))["base"]["active"]


async def test_account_binding_supersession_and_old_observation(db):
    service = Subscriptions(settings(), db, {}, lambda: NOW)
    await service.apply("alice", purchase(), NOW)
    with pytest.raises(DeliveryError, match="purchase_account_mismatch"):
        await service.apply("bob", purchase(), NOW)
    await service.apply("alice", purchase(revoked=True), NOW + timedelta(seconds=1))
    await service.apply("alice", purchase(revoked=False), NOW)
    assert not (await service.snapshot("alice", refresh=False))["base"]["active"]
    # Replacement arrived before its predecessor. A late predecessor must never
    # become a second active subscription even if its API expiry is still future.
    await service.apply("alice", purchase(transaction_id="new", linked_transaction_id="old"), NOW)
    await service.apply("alice", purchase(transaction_id="old"), NOW + timedelta(seconds=1))
    async with db.sessions() as session:
        old = (await session.execute(select(Entitlement).where(Entitlement.transaction_id == "old"))).scalar_one()
        assert old.superseded


async def test_stale_provider_failure_is_unavailable_not_new_paywall(db):
    clock = [NOW]
    service = Subscriptions(settings(), db, {}, lambda: clock[0])
    await service.apply("alice", purchase(), NOW)
    clock[0] += timedelta(minutes=6)
    with pytest.raises(DeliveryError, match="purchase_verification_unavailable"):
        await service.snapshot("alice")


async def test_bot_addon_does_not_include_base(db):
    service = Subscriptions(settings(), db, {}, lambda: NOW)
    await service.apply("alice", purchase("bot_mini"), NOW)
    result = await service.snapshot("alice")
    assert result["bot_mini"]["active"] and not result["bot_mini"]["available"]


def google_document(user_id):
    return {"externalAccountIdentifiers": {"obfuscatedExternalAccountId": billing_account_id(user_id)},
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE", "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING",
        "lineItems": [{"productId": "vipi_base", "expiryTime": "2026-12-24T12:00:00Z",
                       "offerDetails": {"basePlanId": "annual", "offerId": "one_month_trial"}}]}


async def test_google_verifies_product_account_plan_state_and_acknowledges():
    user_id = str(uuid4())
    data = google_document(user_id)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(204) if request.method == "POST" else httpx.Response(200, json=data)
    provider = GoogleProvider(settings(), transport=httpx.MockTransport(respond), credentials=SimpleNamespace(valid=True, token="fixture-only"))
    try:
        result = await provider.verify("opaque/token", user_id, initial=True)
        assert result.product == "base" and not result.revoked
        assert result.trial_ends_at is None  # offer name is not current trial proof
        await provider.acknowledge(result)
        assert calls[-1].url.path.endswith(":acknowledge")
        data["subscriptionState"] = "SUBSCRIPTION_STATE_ON_HOLD"
        assert (await provider.verify("opaque/token", user_id, initial=False)).revoked
        data["externalAccountIdentifiers"]["obfuscatedExternalAccountId"] = "somebody-else"
        with pytest.raises(DeliveryError, match="purchase_account_mismatch"):
            await provider.verify("opaque/token", user_id, initial=True)
        data.update(google_document(user_id)); data["lineItems"][0]["offerDetails"]["basePlanId"] = "monthly"
        with pytest.raises(DeliveryError, match="purchase_invalid"):
            await provider.verify("opaque/token", user_id, initial=True)
        data.update(google_document(user_id)); data["testPurchase"] = {}
        with pytest.raises(DeliveryError, match="purchase_environment_mismatch"):
            await provider.verify("opaque/token", user_id, initial=True)
    finally:
        await provider.close()


async def test_apple_uses_current_status_not_historical_signed_purchase():
    user_id = str(uuid4())
    provider = AppleProvider.__new__(AppleProvider)
    provider.environment = "Sandbox"
    tx = SimpleNamespace(productId="vipi.base.annual", type="Auto-Renewable Subscription",
        appAccountToken=user_id, originalTransactionId="123456", expiresDate=int((NOW + timedelta(days=31)).timestamp()*1000),
        revocationDate=None, offerDiscountType="FREE_TRIAL")
    async def decode(signed):
        assert signed in ("historical-signed-fixture", "current-signed-fixture")
        return tx
    async def status(original):
        assert original == "123456"
        return SimpleNamespace(data=[SimpleNamespace(lastTransactions=[SimpleNamespace(
            originalTransactionId=original, signedTransactionInfo="current-signed-fixture", status=5)])])
    provider.decode = decode
    provider.client = SimpleNamespace(get_all_subscription_statuses=status)
    result = await provider.verify("historical-signed-fixture", user_id, initial=True)
    assert result.revoked  # valid old purchase, current server status is revoked
    with pytest.raises(DeliveryError, match="purchase_account_mismatch"):
        await provider.verify("historical-signed-fixture", str(uuid4()), initial=True)


async def test_purchase_api_does_not_trust_client_grants_or_expose_tokens(db):
    app = create_app(settings(), database=db, verifier=TestVerifier(), clock=lambda: NOW, store_providers={})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as api:
        user, _, headers = await identity(api, "alice")
        state = await api.get("/v1/entitlements", headers=headers)
        assert state.status_code == 200 and state.json()["app_account_token"] == user["id"]
        rejected = await api.post("/v1/purchases/google", headers=headers,
            json={"purchase_token": "sensitive-value", "active": True})
        assert rejected.status_code == 422 and "sensitive" not in rejected.text
        unavailable = await api.post("/v1/purchases/google", headers=headers, json={"purchase_token": "sensitive-value"})
        assert unavailable.status_code == 503 and "sensitive" not in unavailable.text
    await app.state.bot.close()
