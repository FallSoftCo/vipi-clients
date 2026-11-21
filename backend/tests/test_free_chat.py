"""Current free-product contract. Synthetic users, opaque messages, no providers."""
import base64
from datetime import timedelta
from uuid import uuid4
import httpx
from sqlalchemy import select
from conftest import NOW
from test_api import TestVerifier, identity
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import User, VipiTrialEligibility


async def test_free_chat_has_no_trial_deadline_or_store_dependency(db):
    clock = [NOW]
    settings = Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com", service_secret="a"*43, enforce_subscriptions=True)
    app = create_app(settings, database=db, verifier=TestVerifier(), clock=lambda:clock[0], store_providers={})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://vipi.test") as client:
            alice, _, headers = await identity(client,"alice")
            bob, device, bob_headers = await identity(client,"bob")
            async with db.sessions() as session:
                user = await session.get(User,alice["id"])
                assert user.cardless_trial_started_at == user.cardless_trial_ends_at
                assert not (await session.scalars(select(VipiTrialEligibility))).all()
            for days in (0,31,365,1000):
                clock[0] = NOW+timedelta(days=days)
                message = {"id":str(uuid4()),"recipient_id":bob["id"],"recipient_device_id":device,
                    "created_at":clock[0].isoformat(),"cipher_type":3,
                    "ciphertext":base64.b64encode(b"synthetic opaque ciphertext long enough for delivery").decode()}
                result = await client.post("/v1/messages",json=message,headers=headers)
                assert result.status_code == 200, result.text
                assert (await client.get("/v1/messages/pending",headers=bob_headers)).status_code == 200
                state = (await client.get("/v1/entitlements",headers=headers)).json()
                assert state["base"]["active"] and state["base"]["access_source"] == "free"
                assert state["base"]["expires_at"] is None
                assert not any(state["purchases_ready"].values())
                assert not state["bot_mini"]["available"]
            assert (await client.get("/v1/bot/allowance",headers=headers)).status_code == 410
            assert (await client.post("/v1/purchases/google",headers=headers,json={"purchase_token":"synthetic-token"})).status_code == 410
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()


def test_production_free_configuration_does_not_require_billing():
    settings = Settings(environment="production",database_url="postgresql+asyncpg://fixture.invalid/test",
        workos_client_id="client_fixture",workos_issuer="https://api.workos.com",service_secret="a"*43)
    assert not settings.enforce_subscriptions

async def test_free_profile_keeps_previously_verified_paid_right(db):
    from vipi.db import Entitlement
    clock=[NOW]
    settings=Settings(database_url="sqlite+aiosqlite://",workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com",service_secret="a"*43,enforce_subscriptions=True)
    app=create_app(settings,database=db,verifier=TestVerifier(),clock=lambda:clock[0],store_providers={})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://vipi.test") as client:
            user,_,headers=await identity(client,"alice")
            async with db.sessions.begin() as session:
                for product in ("base","bot_mini"):
                    session.add(Entitlement(id=str(uuid4()),user_id=user["id"],product=product,
                        environment="Production",store="apple",transaction_id="prior-"+product,
                        verified_at=NOW,expires_at=NOW+timedelta(days=30),revoked=False,superseded=False))
            active=await client.get("/v1/entitlements",headers=headers)
            assert active.json()["base"]["access_source"]=="free"
            assert active.json()["bot_mini"]["available"] and not any(active.json()["purchases_ready"].values())
            clock[0]+=timedelta(seconds=settings.purchase_outage_seconds+1)
            aged=(await client.get("/v1/entitlements",headers=headers)).json()
            assert aged["base"]["active"] and aged["bot_mini"]["verification_unavailable"]
            assert not aged["bot_mini"]["available"]
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()
