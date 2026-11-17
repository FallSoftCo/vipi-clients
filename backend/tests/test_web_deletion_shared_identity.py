"""Browser deletion binds a signed shared token to WorkOS's raw response ID."""
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from sqlalchemy import select

from test_auth import claims, signing
from test_deletion import settings as base_settings
from test_web_deletion import ORIGIN, HEADERS, Provider, csrf, start
from vipi.api import create_app
from vipi.auth import FixedVerifierSet, WorkOSVerifier
from vipi.db import AccountDeletion, User
from vipi.identity_authorities import FALLSOFT_VIPI, LEGACY_VIPI, canonical_shared_subject
from vipi.web_deletion import AUTH, RECEIPT, START


@pytest.mark.parametrize("case", ["shared", "wrong-response-user", "legacy-token", "wrong-client", "wrong-issuer", "stale-sign-in"])
async def test_shared_callback_only_deletes_verified_namespaced_profile(db, signing, case):
    now = datetime.now(UTC)
    config = base_settings(deletion_web_origin=ORIGIN).model_copy(update={
        "workos_client_id": FALLSOFT_VIPI.client_id, "workos_issuer": FALLSOFT_VIPI.issuer})
    keys = httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [signing[1]]}))
    shared = WorkOSVerifier(config, authority=FALLSOFT_VIPI, transport=keys)
    legacy = WorkOSVerifier(config, authority=LEGACY_VIPI, transport=keys)
    verifier = FixedVerifierSet(shared, legacy)
    provider = Provider()
    # The fixture already contains legacy user_alice. An equal raw ID in the
    # shared realm must neither select nor delete that legacy account.
    provider.user = "user_alice"
    valid_claims = claims(iss=FALLSOFT_VIPI.issuer, client_id=FALLSOFT_VIPI.client_id,
                          sub=provider.user, auth_time=int(now.timestamp()))
    def token(value):
        return jwt.encode(value, signing[0], algorithm="RS256", headers={"kid": "fixture"})
    good_token = token(valid_claims)
    provider.token = good_token
    if case == "wrong-response-user":
        provider.user = "user_bob"
    elif case == "legacy-token":
        provider.token = token(valid_claims | {"iss": LEGACY_VIPI.issuer, "client_id": LEGACY_VIPI.client_id})
    elif case == "wrong-client":
        provider.token = token(valid_claims | {"client_id": "client_unrelated"})
    elif case == "wrong-issuer":
        provider.token = token(valid_claims | {"iss": "https://wrong.invalid"})
    elif case == "stale-sign-in":
        provider.token = token(valid_claims | {"auth_time": int(now.timestamp()) - 601})
    app = create_app(config, database=db, verifier=verifier, clock=lambda: now,
                     web_provider_transport=httpx.MockTransport(provider.request))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as api:
            profile = await api.put("/v1/me", json={"username": "shared_alice", "display_name": "Shared Alice"},
                                    headers={"Authorization": "Bearer " + good_token})
            assert profile.status_code == 200
            account = profile.json()["id"]
            state = await start(api)
            callback = await api.get("/delete-account/callback", params={"state": state, "code": "fixture-code"})
            assert len(provider.calls) == 1
            assert provider.calls[0]["client_id"] == FALLSOFT_VIPI.client_id
            async with db.sessions() as session:
                assert (await session.get(User, account)).subject == canonical_shared_subject("user_alice")
                assert (await session.get(User, "alice")).subject == "user_alice"
                assert not list((await session.scalars(select(AccountDeletion))).all())
            if case != "shared":
                assert callback.status_code == 401
                assert AUTH not in api.cookies and RECEIPT not in api.cookies and START not in api.cookies
                return
            assert callback.status_code == 303
            confirmation = await api.get(callback.headers["location"])
            assert "@shared_alice" in confirmation.text
            saved = httpx.Cookies(api.cookies)
            result = await api.post("/delete-account/confirm", data={"csrf": csrf(confirmation)}, headers=HEADERS)
            assert result.status_code == 303
            # A lost POST response must still recover the exact shared receipt.
            api.cookies = saved
            assert "Vipi account deleted" in (await api.get("/delete-account")).text
            async with db.sessions() as session:
                assert await session.get(User, account) is None
                assert await session.get(User, "alice") is not None
                assert await session.get(User, "bob") is not None
                assert (await session.get(AccountDeletion, account)).finished_at is not None
            assert len(provider.calls) == 1  # No WorkOS account deletion request.
    finally:
        await shared.close()
        await legacy.close()
