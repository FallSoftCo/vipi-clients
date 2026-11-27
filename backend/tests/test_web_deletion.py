from datetime import timedelta
import re
import secrets
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

from conftest import NOW
from test_api import TestVerifier
from test_deletion import settings as base_settings
from vipi.api import create_app
from vipi.auth import Principal
from vipi.db import AccountDeletion, User
from vipi.deletion import request_deletion, lock_account_lifecycle
from vipi.web_deletion import AUTH, RECEIPT, START

ORIGIN = "https://vipi.test"
HEADERS = {"Origin": ORIGIN}


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


class Provider:
    def __init__(self):
        self.calls = []
        self.user = "user_qa_alice"
        self.token = "alice"
        self.email = "fixture@vipi.test"
        self.fail = False

    async def request(self, request):
        import json

        body = json.loads(request.content)
        assert str(request.url) == "https://api.workos.com/user_management/authenticate"
        assert body["grant_type"] == "authorization_code" and body["code_verifier"]
        assert body["client_secret"] == "test-key-never-live"
        self.calls.append(body)
        if self.fail:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "access_token": self.token,
                "user": {"id": self.user, "email": self.email},
            },
        )


def application(db, provider, *, verifier=None, clock=lambda: NOW):
    return create_app(
        base_settings(deletion_web_origin=ORIGIN),
        database=db,
        verifier=verifier or TestVerifier(),
        clock=clock,
        web_provider_transport=httpx.MockTransport(provider.request),
    )


async def start(api):
    landing = await api.get("/delete-account")
    response = await api.get("/delete-account/sign-in")
    assert response.status_code == 303
    target = urlsplit(response.headers["location"])
    assert target.scheme == "https" and target.netloc == "api.workos.com"
    params = parse_qs(target.query)
    assert params["max_age"] == ["0"] and params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [ORIGIN + "/delete-account/callback"]
    return params["state"][0]


async def finish(api, state):
    response = await api.get(
        "/delete-account/callback", params={"state": state, "code": "fixture-code"}
    )
    assert response.status_code == 303
    return await api.get(response.headers["location"])


async def test_web_deletion_confirms_exact_account_and_survives_lost_response(db):
    provider = Provider()
    app = application(db, provider)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        profile = await api.put(
            "/v1/me",
            json={"username": "qa_alice", "display_name": "Alice"},
            headers={"Authorization": "Bearer alice"},
        )
        account = profile.json()["id"]
        confirm = await finish(api, await start(api))
        assert "@qa_alice" in confirm.text and "This cannot be undone" in confirm.text
        assert (
            "test-key-never-live" not in confirm.text
            and "fixture-code" not in confirm.text
        )
        saved = httpx.Cookies(api.cookies)
        # Neither landing nor callback deleted any user.
        async with db.sessions() as s:
            assert await s.get(User, account)
        response = await api.post(
            "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
        )
        assert response.status_code == 303
        # Discard the POST response's cookies as if the response never arrived.
        api.cookies = saved
        pending = await api.get("/delete-account")
        assert (
            "Vipi account deleted" in pending.text
            and "shared Fallsoft sign-in" in pending.text
        )
        assert AUTH not in api.cookies and START not in api.cookies
        finished = await api.get("/delete-account")
        assert "Vipi account deleted" in finished.text
        async with db.sessions() as s:
            assert await s.get(User, account) is None
            assert await s.get(User, "bob") is not None
            assert (await s.get(AccountDeletion, account)).subject is None


async def test_web_deletion_cancel_and_unfinished_onboarding(db):
    provider = Provider()
    provider.email = '<img src=x onerror="alert(1)">@vipi.test'
    app = application(db, provider)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        confirm = await finish(api, await start(api))
        assert "&lt;img" in confirm.text and "<img" not in confirm.text
        response = await api.post(
            "/delete-account/cancel", data={"csrf": csrf(confirm)}, headers=HEADERS
        )
        assert "Deletion canceled" in response.text and not api.cookies
        async with db.sessions() as s:
            assert not list((await s.scalars(select(AccountDeletion))).all())
        confirm = await finish(api, await start(api))
        response = await api.post(
            "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
        )
        assert response.status_code == 303
        assert "Vipi account deleted" in (await api.get("/delete-account")).text
        async with db.sessions() as s:
            assert (await s.scalar(select(AccountDeletion))).subject is None
            assert len((await s.scalars(select(User))).all()) == 3


async def test_web_deletion_rejects_csrf_tampering_and_wrong_oauth_state(db):
    provider = Provider()
    app = application(db, provider)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        state = await start(api)
        for params in [
            {"state": "wrong", "code": "fixture"},
            [("state", state), ("state", state), ("code", "fixture")],
        ]:
            assert (
                await api.get("/delete-account/callback", params=params)
            ).status_code == 400
        assert not provider.calls
        confirm = await finish(api, state)
        for hdr, data in [
            ({}, {"csrf": csrf(confirm)}),
            ({"Origin": "https://attacker.test"}, {"csrf": csrf(confirm)}),
            (HEADERS, {"csrf": "wrong"}),
        ]:
            assert (
                await api.post("/delete-account/confirm", data=data, headers=hdr)
            ).status_code == 403
        api.cookies.set(AUTH, "tampered", domain="vipi.test", path="/")
        assert (
            await api.post(
                "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
            )
        ).status_code == 403
        async with db.sessions() as s:
            assert not list((await s.scalars(select(AccountDeletion))).all())


async def test_web_deletion_expired_session_and_provider_failure_do_not_delete(db):
    provider = Provider()
    provider.fail = True
    current = [NOW]
    app = application(db, provider, clock=lambda: current[0])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        state = await start(api)
        failed = await api.get(
            "/delete-account/callback", params={"state": state, "code": "fixture"}
        )
        assert failed.status_code == 401 and START not in api.cookies
        provider.fail = False
        confirm = await finish(api, await start(api))
        current[0] = NOW + timedelta(seconds=601)
        assert (
            await api.post(
                "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
            )
        ).status_code == 403
        assert "Sign in to continue" in (await api.get("/delete-account")).text
        async with db.sessions() as s:
            assert not list((await s.scalars(select(AccountDeletion))).all())


async def test_web_deletion_identity_mismatch_and_stale_auth_time_are_rejected(db):
    class Stale(TestVerifier):
        async def verify(self, token):
            return Principal("user_qa_alice", "fixture", int(NOW.timestamp()) - 601)

    for verifier, user in [
        (TestVerifier(), "user_someone_else"),
        (Stale(), "user_qa_alice"),
    ]:
        provider = Provider()
        provider.user = user
        app = application(db, provider, verifier=verifier)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as api:
            state = await start(api)
            response = await api.get(
                "/delete-account/callback", params={"state": state, "code": "fixture"}
            )
            assert response.status_code == 401 and AUTH not in api.cookies


async def test_web_receipt_handles_native_deletion_started_after_confirmation(db):
    provider = Provider()
    app = application(db, provider)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        confirm = await finish(api, await start(api))
        # A different, legitimate UUID/capability from unfinished native setup.
        async with db.sessions.begin() as s:
            await request_deletion(
                s,
                subject="user_qa_alice",
                account_id=str(uuid4()),
                receipt_secret=secrets.token_urlsafe(32),
                service_secret=base_settings().service_secret,
                now=NOW,
            )
        response = await api.post(
            "/delete-account/cancel", data={"csrf": csrf(confirm)}, headers=HEADERS
        )
        assert (
            "Vipi account deleted" in response.text
            and "Deletion canceled" not in response.text
        )
        assert "Vipi account deleted" in (await api.get("/delete-account")).text


async def test_browser_headers_cookies_and_disabled_service(db):
    provider = Provider()
    app = application(db, provider)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        response = await api.get("/delete-account")
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert response.headers["referrer-policy"] == "same-origin"
        cookies = response.headers.get_list("set-cookie")
        assert all(
            "Secure" in c
            and "HttpOnly" in c
            and "SameSite=lax" in c
            and "Domain=" not in c
            for c in cookies
        )
        confirm = await finish(api, await start(api))
        assert AUTH in api.cookies and RECEIPT in api.cookies
        assert all(len(c.value) < 3800 for c in api.cookies.jar)
        assert (await api.get("/delete-account/style.css")).status_code == 200
    disabled = create_app(
        base_settings(), database=db, verifier=TestVerifier(), clock=lambda: NOW
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=disabled), base_url=ORIGIN
    ) as api:
        assert (await api.get("/delete-account")).status_code == 503


def test_browser_requires_exact_configured_https_origin():
    for value in [
        "http://vipi.test",
        "https://vipi.test/",
        "https://user@vipi.test",
        "https://vipi.test/?evil=1",
    ]:
        with pytest.raises(ValueError):
            base_settings(deletion_web_origin=value)


async def test_browser_confirmation_waiting_behind_native_deletion_recovers(db):
    import asyncio

    if db.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL advisory lock interleaving")
    app = application(db, Provider())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        confirm = await finish(api, await start(api))
        task = None
        try:
            async with db.sessions.begin() as native:
                await lock_account_lifecycle(
                    native, "user_qa_alice", base_settings().service_secret
                )
                task = asyncio.create_task(
                    api.post(
                        "/delete-account/confirm",
                        data={"csrf": csrf(confirm)},
                        headers=HEADERS,
                    )
                )
                for _ in range(100):
                    async with db.sessions() as observer:
                        waiting = await observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event='advisory'"
                            )
                        )
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
                assert waiting and not task.done(), (
                    "Browser did not wait for the native account transaction"
                )
                await request_deletion(
                    native,
                    subject="user_qa_alice",
                    account_id=str(uuid4()),
                    receipt_secret=secrets.token_urlsafe(32),
                    service_secret=base_settings().service_secret,
                    now=NOW,
                )
            assert (await asyncio.wait_for(task, 5)).status_code == 303
            assert "Vipi account deleted" in (await api.get("/delete-account")).text
            async with db.sessions() as session:
                assert len((await session.scalars(select(AccountDeletion))).all()) == 1
        finally:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def test_unadmitted_staging_identity_can_delete_its_own_account_but_cannot_chat(
    db,
):
    provider = Provider()
    # Validate an inert PG deployment config; db remains the explicitly injected fixture.
    stage = base_settings(deletion_web_origin=ORIGIN)
    stage = type(stage).model_validate(
        stage.model_dump()
        | {
            "database_url": "postgresql+asyncpg://fixture.invalid/vipi_test",
            "environment": "staging",
            "allowed_subjects": frozenset(["user_qa_other"]),
        }
    )
    app = create_app(
        stage,
        database=db,
        verifier=TestVerifier(),
        clock=lambda: NOW,
        web_provider_transport=httpx.MockTransport(provider.request),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        headers = {"Authorization": "Bearer alice"}
        assert (await api.get("/v1/me", headers=headers)).status_code == 403
        assert (
            await api.put(
                "/v1/me",
                json={"username": "new_person", "display_name": "QA"},
                headers=headers,
            )
        ).status_code == 403
        confirm = await finish(api, await start(api))
        assert "Delete your Vipi account?" in confirm.text
        native = await api.request(
            "DELETE",
            "/v1/me",
            headers=headers,
            json={
                "account_id": str(uuid4()),
                "receipt_secret": secrets.token_urlsafe(32),
            },
        )
        assert native.status_code == 202
        assert "Vipi account deleted" in (await api.get("/delete-account")).text
        async with db.sessions() as session:
            assert len((await session.scalars(select(User))).all()) == 3


async def test_web_old_receipt_cannot_delete_rejoined_profile_and_new_sign_in_can_review_it(
    db,
):
    current = [NOW]

    class Verifier(TestVerifier):
        async def verify(self, token):
            if token == "fresh-alice":
                return Principal(
                    "user_qa_alice", "new-session", int(current[0].timestamp())
                )
            return await super().verify(token)

    provider = Provider()
    app = application(db, provider, verifier=Verifier(), clock=lambda: current[0])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as api:
        old = {"Authorization": "Bearer alice"}
        first = (
            await api.put(
                "/v1/me",
                headers=old,
                json={"username": "qa_alice", "display_name": "Alice"},
            )
        ).json()
        confirm = await finish(api, await start(api))
        old_cookies = httpx.Cookies(api.cookies)
        assert (
            await api.post(
                "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
            )
        ).status_code == 303
        current[0] += timedelta(seconds=2)
        fresh = {"Authorization": "Bearer fresh-alice"}
        second = (
            await api.put(
                "/v1/me",
                headers=fresh,
                json={"username": "new_alice", "display_name": "New"},
            )
        ).json()
        assert second["id"] != first["id"]
        api.cookies = old_cookies
        # An old browser confirmation observes only the old deletion.
        old_result = await api.post(
            "/delete-account/confirm", data={"csrf": csrf(confirm)}, headers=HEADERS
        )
        assert "Vipi account deleted" in old_result.text
        assert (await api.get("/v1/me", headers=fresh)).json()["id"] == second["id"]
        provider.token = "fresh-alice"
        new_confirm = await finish(api, await start(api))
        assert (
            "@new_alice" in new_confirm.text
            and "Delete your Vipi account?" in new_confirm.text
        )
        assert (
            await api.post(
                "/delete-account/confirm",
                data={"csrf": csrf(new_confirm)},
                headers=HEADERS,
            )
        ).status_code == 303
        assert "shared Fallsoft sign-in" in (await api.get("/delete-account")).text
        async with db.sessions() as session:
            rows = (await session.scalars(select(AccountDeletion))).all()
            assert len(rows) == 2 and len({x.subject_hash for x in rows}) == 1
            assert all(x.finished_at is not None and x.subject is None for x in rows)
        assert all(
            call["grant_type"] == "authorization_code" for call in provider.calls
        )
