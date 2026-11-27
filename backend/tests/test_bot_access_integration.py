"""HTTP regressions for retired bot routes and authenticated free-chat access.

Synthetic identities only. The provider is a local MockTransport; denied requests
must not reserve quota, contact the provider, or fabricate store entitlements.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
import secrets
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from test_subscriptions import settings
from vipi.api import create_app
from vipi.auth import AuthenticationError, Principal
from vipi.db import BotPool, BotReport, Entitlement, Reservation, UsageBucket, User
from vipi.identity_authorities import FALLSOFT_VIPI, LEGACY_VIPI

OWNER = "31111111-1111-4111-8111-111111111111"
PINNED = "32222222-2222-4222-8222-222222222222"
LEGACY = "33333333-3333-4333-8333-333333333333"
SUBJECTS = {
    "owner": "fallsoft-vipi-production:user_actual_owned_fixture",
    "pinned": "fallsoft-vipi-production:user_previously_pinned_fixture",
    "legacy": "user_actual_owned_fixture",
}
IDS = {"owner": OWNER, "pinned": PINNED, "legacy": LEGACY}


class Verifier:
    async def verify(self, token):
        who = token.removesuffix("_old")
        if who not in SUBJECTS:
            raise AuthenticationError("invalid")
        auth_time = NOW - timedelta(hours=2) if token.endswith("_old") else NOW
        authority = LEGACY_VIPI.id if who == "legacy" else FALLSOFT_VIPI.id
        return Principal(
            SUBJECTS[who], "synthetic_session", int(auth_time.timestamp()), authority
        )


@pytest.fixture
async def owned_accounts(db):
    async with db.sessions.begin() as session:
        for who, uid in IDS.items():
            session.add(
                User(
                    id=uid,
                    subject=SUBJECTS[who],
                    username="synthetic_" + who,
                    display_name="Synthetic tester",
                    created_at=NOW - timedelta(days=1),
                    cardless_trial_started_at=NOW - timedelta(days=1),
                    cardless_trial_ends_at=NOW + timedelta(days=29),
                )
            )
    return db


def auth(who):
    return {"Authorization": "Bearer " + who}


@asynccontextmanager
async def application(db, calls, **options):
    def provider(request):
        calls.append(request)
        raise AssertionError("Disabled route contacted bot provider")

    app = create_app(
        settings(
            deepseek_api_key="synthetic_only", enforce_subscriptions=True, **options
        ),
        database=db,
        verifier=Verifier(),
        clock=lambda: NOW,
        store_providers={},
        bot_transport=httpx.MockTransport(provider),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            yield client
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()


async def register(client, who="owner", *, replace=False):
    device, secret = str(uuid4()), secrets.token_urlsafe(32)
    result = await client.post(
        "/v1/devices",
        headers=auth(who),
        json={"device_id": device, "secret": secret, "replace_active": replace},
    )
    assert result.status_code == 200, result.text
    return auth(who) | {"X-Vipi-Device-ID": device, "X-Vipi-Device-Secret": secret}


async def send(client, headers, request_id=None, **body):
    return await client.post(
        "/v1/bot/messages",
        headers=headers,
        json={
            "request_id": request_id or str(uuid4()),
            "consent_version": "deepseek-v1",
            "messages": [{"role": "user", "content": "Synthetic hello"}],
            **body,
        },
    )


@pytest.mark.parametrize("who", ["owner", "pinned", "legacy"])
async def test_disabled_bot_routes_do_not_dispatch_or_persist(owned_accounts, who):
    calls = []
    async with application(
        owned_accounts,
        calls,
        reviewer_identity_subjects={SUBJECTS["pinned"]},
        reviewer_user_ids={OWNER},
    ) as client:
        headers = await register(client, who)
        request_id = str(uuid4())
        report = {
            "request_id": request_id,
            "reason": "other",
            "selected_reply": "Synthetic reply",
        }
        for result in (
            await client.get("/v1/bot/allowance", headers=headers),
            await send(client, headers, request_id),
            await send(client, headers, request_id),
            await client.post("/v1/bot/reports", headers=headers, json=report),
        ):
            assert result.status_code == 410
            assert result.json() == {"error": "bot_unavailable"}
        assert (await send(client, {})).status_code == 401
    assert not calls
    async with owned_accounts.sessions() as session:
        for table in (Reservation, BotPool, Entitlement, BotReport):
            assert not (await session.scalars(select(table))).all()
        assert not (
            await session.scalars(
                select(UsageBucket).where(UsageBucket.user_id == IDS[who])
            )
        ).all()


async def test_only_current_owned_device_can_read_free_inbox(owned_accounts):
    async with application(owned_accounts, [], reviewer_user_ids={OWNER}) as client:
        old = await register(client)
        current = await register(client, replace=True)
        foreign = await register(client, "pinned")
        for headers in (
            old,
            auth("owner"),
            foreign | auth("owner"),
            current | {"X-Vipi-Device-Secret": secrets.token_urlsafe(32)},
        ):
            denied = await client.get("/v1/messages/pending", headers=headers)
            assert denied.status_code == 401 and denied.json() == {
                "error": "device_revoked"
            }
        malformed = await client.get(
            "/v1/messages/pending",
            headers=current | {"X-Vipi-Device-Secret": "too_short"},
        )
        assert malformed.status_code == 401 and malformed.json() == {
            "error": "invalid_device_credential"
        }
        assert (
            await client.get("/v1/messages/pending", headers=current)
        ).status_code == 200


async def test_existing_device_preserves_fresh_auth_and_account_revocation_rules(
    owned_accounts,
):
    async with application(owned_accounts, [], reviewer_user_ids={OWNER}) as client:
        registered = await register(client)
        old_auth = registered | auth("owner_old")
        assert (await client.get("/v1/keys", headers=old_auth)).status_code == 200
        denied = await client.post(
            "/v1/devices",
            headers=old_auth,
            json={
                "device_id": registered["X-Vipi-Device-ID"],
                "secret": registered["X-Vipi-Device-Secret"],
            },
        )
        assert denied.status_code == 401 and denied.json() == {
            "error": "recent_sign_in_required"
        }
        assert (
            await client.get("/v1/messages/pending", headers=old_auth)
        ).status_code == 200
        async with owned_accounts.sessions.begin() as session:
            (await session.get(User, OWNER)).minimum_auth_time = int(NOW.timestamp())
        for path in ("/v1/me", "/v1/entitlements", "/v1/messages/pending"):
            rejected = await client.get(path, headers=old_auth)
            assert rejected.status_code == 401 and rejected.json() == {
                "error": "recent_sign_in_required"
            }
            assert (await client.get(path, headers=registered)).status_code == 200
