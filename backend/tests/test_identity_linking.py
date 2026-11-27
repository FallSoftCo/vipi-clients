import secrets
from datetime import timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from sqlalchemy import select

from conftest import NOW
from test_api import identity
from test_auth import signing, claims
from vipi.api import create_app
from vipi.auth import AuthenticationError, Principal, WorkOSVerifier
from vipi.config import Settings
from vipi.db import (
    BillingAccountBinding,
    Device,
    Entitlement,
    IdentityAuthorityAlias,
    IdentityLinkReceipt,
    User,
    VipiTrialEligibility,
    VipiTrialEligibilityLink,
)
from vipi.deletion import request_deletion
from vipi.eligibility import (
    eligibility_hash,
    erase_for_global_fallsoft_deletion,
    original_trial,
)
from vipi.identity_authorities import (
    FALLSOFT_VIPI,
    LEGACY_VIPI,
    canonical_shared_subject,
)

SECRET = "identity-link-fixture-" * 3


def settings(**changes):
    return Settings(
        database_url="sqlite+aiosqlite://",
        workos_client_id=LEGACY_VIPI.client_id,
        workos_issuer=LEGACY_VIPI.issuer,
        service_secret=SECRET,
        shared_identity_transition_enabled=True,
        **changes,
    )


class LegacyVerifier:
    async def verify(self, token):
        subject = token.removeprefix("stale-")
        if subject not in ("alice", "bob", "eve"):
            raise AuthenticationError()
        return Principal(
            "user_qa_" + subject,
            "session_fixture",
            int(NOW.timestamp()) - (601 if token.startswith("stale-") else 0),
            LEGACY_VIPI.id,
        )


class SharedVerifier:
    async def verify(self, token):
        if token not in ("shared-alice", "shared-eve", "shared-same", "shared-stale"):
            raise AuthenticationError()
        raw = (
            "user_qa_alice"
            if token == "shared-same"
            else "user_shared_eve"
            if token == "shared-eve"
            else "user_shared_alice"
        )
        return Principal(
            canonical_shared_subject(raw),
            "shared_session_fixture",
            int(NOW.timestamp()) - (601 if token == "shared-stale" else 0),
            FALLSOFT_VIPI.id,
        )


def client(db, **config):
    app = create_app(
        settings(**config),
        database=db,
        verifier=LegacyVerifier(),
        shared_verifier=SharedVerifier(),
        clock=lambda: NOW,
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    )


async def test_explicit_link_preserves_account_device_purchase_and_original_trial(db):
    async with client(db) as api:
        account, device, headers = await identity(api, "alice")
        async with db.sessions.begin() as session:
            # A pre-free profile must be seeded explicitly; new profile creation
            # now has zero-length dates and creates no trial identity.
            historical = await session.get(User, account["id"])
            historical.cardless_trial_started_at = NOW - timedelta(days=30)
            historical.cardless_trial_ends_at = NOW
            before = (await session.get(Device, device)).credential_hash
            session.add(
                Entitlement(
                    id="link-purchase",
                    user_id=account["id"],
                    product="base",
                    store="test",
                    transaction_id="link-fixture",
                    environment="Unknown",
                    expires_at=NOW + timedelta(days=10),
                )
            )
            await original_trial(
                session,
                subject=canonical_shared_subject("user_shared_alice"),
                service_secret=SECRET,
                started_at=NOW - timedelta(days=45),
                ends_at=NOW - timedelta(days=15),
            )
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        response = await api.post(
            "/v1/identity-links/fallsoft", headers=headers, json=body
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "request_id": body["request_id"],
            "account_id": account["id"],
            "authority_id": FALLSOFT_VIPI.id,
            "authentication_subject": "user_shared_alice",
            "binding_revision": 1,
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).json() == response.json()
        assert (
            await api.get("/v1/me", headers={"Authorization": "Bearer shared-alice"})
        ).json() == account
        assert (await api.get("/v1/me", headers=headers)).status_code == 404
        assert (
            await api.put(
                "/v1/me",
                headers=headers,
                json={"username": "another_profile", "display_name": "Wrong"},
            )
        ).json() == {"error": "fallsoft_sign_in_required"}
        async with db.sessions() as session:
            user = await session.get(User, account["id"])
            assert user.subject == canonical_shared_subject("user_shared_alice")
            assert user.username == account["username"]
            assert user.cardless_trial_ends_at.replace(
                tzinfo=NOW.tzinfo
            ) == NOW - timedelta(days=15)
            assert (await session.get(Device, device)).credential_hash == before
            assert (await session.get(Entitlement, "link-purchase")).user_id == account[
                "id"
            ]
            receipt = await session.get(IdentityLinkReceipt, body["request_id"])
            assert (
                receipt.source_hash != "user_qa_alice"
                and receipt.target_hash != user.subject
            )
            assert set(receipt.__table__.columns.keys()) == {
                "request_id",
                "account_id",
                "source_hash",
                "target_hash",
                "device_hash",
                "created_at",
            }
            for subject in ("user_qa_alice", user.subject):
                ledger = await session.get(
                    VipiTrialEligibility, eligibility_hash(subject, SECRET)
                )
                assert ledger.ends_at.replace(tzinfo=NOW.tzinfo) == NOW - timedelta(
                    days=15
                )


@pytest.mark.parametrize(
    "case",
    [
        "stale-source",
        "stale-target",
        "wrong-device",
        "wrong-account",
        "occupied",
        "wrong-authority",
    ],
)
async def test_invalid_link_proofs_never_change_either_account(db, case):
    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        if case == "stale-source":
            headers = headers | {"Authorization": "Bearer stale-alice"}
        if case == "stale-target":
            body["fallsoft_access_token"] = "shared-stale"
        if case == "wrong-device":
            headers = headers | {"X-Vipi-Device-Secret": secrets.token_urlsafe(32)}
        if case == "wrong-account":
            body["expected_account_id"] = str(uuid4())
        if case == "wrong-authority":
            headers = headers | {"Authorization": "Bearer shared-eve"}
        if case == "occupied":
            occupied = await api.put(
                "/v1/me",
                headers={"Authorization": "Bearer shared-alice"},
                json={"username": "shared_existing", "display_name": "Existing"},
            )
            assert occupied.status_code == 200
        response = await api.post(
            "/v1/identity-links/fallsoft", headers=headers, json=body
        )
        assert response.status_code in (401, 409)
        async with db.sessions() as session:
            assert (await session.get(User, account["id"])).subject == "user_qa_alice"
            assert await session.get(IdentityLinkReceipt, body["request_id"]) is None


async def test_namespaces_prevent_equal_raw_subject_from_claiming_legacy_account(db):
    async with client(db) as api:
        legacy, _, _ = await identity(api, "alice")
        shared = await api.put(
            "/v1/me",
            headers={"Authorization": "Bearer shared-same"},
            json={"username": "shared_distinct", "display_name": "Distinct"},
        )
        assert shared.status_code == 200 and shared.json()["id"] != legacy["id"]
        assert (
            await api.get("/v1/me", headers={"Authorization": "Bearer alice"})
        ).json() == legacy


async def test_link_receipt_rejects_changed_target_and_second_request_without_reassigning(
    db,
):
    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).status_code == 200
        assert (
            await api.post(
                "/v1/identity-links/fallsoft",
                headers=headers,
                json=body | {"fallsoft_access_token": "shared-eve"},
            )
        ).status_code == 409
        assert (
            await api.post(
                "/v1/identity-links/fallsoft",
                headers=headers,
                json=body | {"request_id": str(uuid4())},
            )
        ).status_code == 409
        assert (
            await api.get("/v1/me", headers={"Authorization": "Bearer shared-alice"})
        ).json() == account


async def test_app_delete_retains_only_trial_hmac_links_and_global_hook_erases_linked_eligibility(
    db,
):
    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        async with db.sessions.begin() as session:
            historical = await session.get(User, account["id"])
            historical.cardless_trial_started_at = NOW - timedelta(days=30)
            historical.cardless_trial_ends_at = NOW
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).status_code == 200
    target = canonical_shared_subject("user_shared_alice")
    async with db.sessions.begin() as session:
        await request_deletion(
            session,
            subject=target,
            account_id=account["id"],
            receipt_secret=secrets.token_urlsafe(32),
            service_secret=SECRET,
            now=NOW,
        )
        await original_trial(
            session, subject="user_unrelated", service_secret=SECRET, started_at=NOW
        )
    async with db.sessions() as session:
        assert await session.get(IdentityLinkReceipt, body["request_id"]) is None
        assert len((await session.scalars(select(VipiTrialEligibilityLink))).all()) == 1
    async with client(db) as api:
        # Removing the Vipi profile must not let the original pre-deletion
        # legacy sign-in silently provision a second profile.
        assert (
            await api.put(
                "/v1/me",
                headers={"Authorization": "Bearer alice"},
                json={"username": "parallel_profile", "display_name": "Wrong"},
            )
        ).json() == {"error": "fallsoft_sign_in_required"}
    async with db.sessions.begin() as session:
        await erase_for_global_fallsoft_deletion(
            session, subject=target, service_secret=SECRET
        )
    async with db.sessions() as session:
        assert (await session.scalars(select(VipiTrialEligibilityLink))).all() == []
        assert [
            r.subject_hash
            for r in (await session.scalars(select(VipiTrialEligibility))).all()
        ] == [eligibility_hash("user_unrelated", SECRET)]


async def test_shared_signature_still_requires_vipi_application_audience_and_exact_issuer(
    signing,
):
    verifier = WorkOSVerifier(
        settings(),
        authority=FALLSOFT_VIPI,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"keys": [signing[1]]})
        ),
    )
    try:
        valid = claims(iss=FALLSOFT_VIPI.issuer, client_id=FALLSOFT_VIPI.client_id)
        token = jwt.encode(
            valid, signing[0], algorithm="RS256", headers={"kid": "fixture"}
        )
        principal = await verifier.verify(token)
        assert (
            principal.subject == canonical_shared_subject("user_fixture")
            and principal.authority == FALLSOFT_VIPI.id
        )
        # Both observed environments use the same exact issuer. Audience and
        # fixed key authority must still isolate legacy, Vipi and company login.
        for patch in (
            {"client_id": "client_01JPK69ZZFHH0NSP8BY2HGRDX6"},
            {"client_id": LEGACY_VIPI.client_id},
            {"iss": "https://api.workos.com/"},
            {
                "iss": "https://api.workos.com/user_management/client_01JPK69ZZFHH0NSP8BY2HGRDX6"
            },
            {
                "iss": "https://api.workos.com/user_management/"
                + FALLSOFT_VIPI.client_id
            },
        ):
            with pytest.raises(AuthenticationError):
                await verifier.verify(
                    jwt.encode(
                        valid | patch,
                        signing[0],
                        algorithm="RS256",
                        headers={"kid": "fixture"},
                    )
                )
    finally:
        await verifier.close()


async def test_legacy_transition_uses_observed_session_issuer_and_keeps_application_isolation(
    signing,
):
    # A real owned-reviewer session uses this exact issuer, despite the public
    # discovery document advertising a client-suffixed value.
    configured = Settings(
        database_url="sqlite+aiosqlite://",
        workos_client_id=LEGACY_VIPI.client_id,
        workos_issuer="https://api.workos.com",
        service_secret=SECRET,
        shared_identity_transition_enabled=True,
    )
    verifier = WorkOSVerifier(
        configured,
        authority=LEGACY_VIPI,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"keys": [signing[1]]})
        ),
    )
    valid = claims(iss="https://api.workos.com", client_id=LEGACY_VIPI.client_id)
    try:
        principal = await verifier.verify(
            jwt.encode(valid, signing[0], algorithm="RS256", headers={"kid": "fixture"})
        )
        assert (
            principal.authority == LEGACY_VIPI.id
            and principal.subject == "user_fixture"
        )
        for patch in (
            {"iss": "https://api.workos.com/"},
            {"iss": "https://api.workos.com/user_management/" + LEGACY_VIPI.client_id},
            {
                "iss": "https://api.workos.com/user_management/client_01JPK69ZZFHH0NSP8BY2HGRDX6"
            },
            {"client_id": FALLSOFT_VIPI.client_id},
            {"client_id": "client_01JPK69ZZFHH0NSP8BY2HGRDX6"},
        ):
            with pytest.raises(AuthenticationError):
                await verifier.verify(
                    jwt.encode(
                        valid | patch,
                        signing[0],
                        algorithm="RS256",
                        headers={"kid": "fixture"},
                    )
                )
    finally:
        await verifier.close()


def test_transition_never_accepts_arbitrary_configured_authority():
    with pytest.raises(ValueError, match="pinned authority"):
        Settings(
            database_url="sqlite+aiosqlite://",
            workos_client_id="client_unknown",
            workos_issuer="https://attacker.invalid",
            service_secret=SECRET,
            shared_identity_transition_enabled=True,
        )


async def test_link_transaction_failure_rolls_back_subject_receipt_and_trial_mapping(
    db,
):
    from vipi.identity_linking import link_identity

    async with client(db) as api:
        account, device, headers = await identity(api, "alice")
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        async with db.sessions.begin() as session:
            await link_identity(
                session,
                source=await LegacyVerifier().verify("alice"),
                target=await SharedVerifier().verify("shared-alice"),
                request_id=str(uuid4()),
                account_id=account["id"],
                device_id=device,
                device_secret=headers["X-Vipi-Device-Secret"],
                service_secret=SECRET,
                now=NOW,
            )
            raise RuntimeError("synthetic rollback")
    async with db.sessions() as session:
        assert (await session.get(User, account["id"])).subject == "user_qa_alice"
        assert (await session.scalars(select(IdentityLinkReceipt))).all() == []
        assert (await session.scalars(select(VipiTrialEligibilityLink))).all() == []


async def test_concurrent_exact_link_retry_has_one_receipt_and_one_account(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Requires actual transaction-scoped PostgreSQL lifecycle locks")
    import asyncio

    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        replies = await asyncio.gather(
            *(
                api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
                for _ in range(2)
            )
        )
        assert [r.status_code for r in replies] == [200, 200]
        assert replies[0].json() == replies[1].json()
    async with db.sessions() as session:
        assert len((await session.scalars(select(IdentityLinkReceipt))).all()) == 1


async def test_free_link_does_not_create_trial_eligibility_or_grant_paid_access(db):
    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).status_code == 200
        assert (
            await api.get("/v1/me", headers={"Authorization": "Bearer shared-alice"})
        ).json() == account
        async with db.sessions() as session:
            user = await session.get(User, account["id"])
            assert user.cardless_trial_started_at == user.cardless_trial_ends_at
            assert not (await session.scalars(select(VipiTrialEligibility))).all()
            assert not (await session.scalars(select(VipiTrialEligibilityLink))).all()
            assert not (
                await session.scalars(
                    select(Entitlement).where(Entitlement.user_id == user.id)
                )
            ).all()
            assert not (await session.scalars(select(BillingAccountBinding))).all()


async def test_deleted_free_link_blocks_former_identity_without_creating_trial_records(
    db,
):
    target = canonical_shared_subject("user_shared_alice")
    async with client(db) as api:
        account, _, headers = await identity(api, "alice")
        body = {
            "request_id": str(uuid4()),
            "expected_account_id": account["id"],
            "fallsoft_access_token": "shared-alice",
        }
        assert (
            await api.post("/v1/identity-links/fallsoft", headers=headers, json=body)
        ).status_code == 200
        async with db.sessions.begin() as session:
            await request_deletion(
                session,
                subject=target,
                account_id=account["id"],
                receipt_secret=secrets.token_urlsafe(32),
                service_secret=SECRET,
                now=NOW,
            )
        response = await api.put(
            "/v1/me",
            headers={"Authorization": "Bearer alice"},
            json={"username": "parallel_free", "display_name": "Wrong"},
        )
        assert response.status_code == 409 and response.json() == {
            "error": "fallsoft_sign_in_required"
        }
        async with db.sessions() as session:
            assert await session.get(IdentityLinkReceipt, body["request_id"]) is None
            alias = await session.get(
                IdentityAuthorityAlias, eligibility_hash("user_qa_alice", SECRET)
            )
            assert alias.target_hash == eligibility_hash(target, SECRET)
            assert set(alias.__table__.columns.keys()) == {"source_hash", "target_hash"}
            assert not (await session.scalars(select(VipiTrialEligibility))).all()
            assert not (await session.scalars(select(VipiTrialEligibilityLink))).all()
        # The separately confirmed global erasure also removes generic aliases.
        async with db.sessions.begin() as session:
            await erase_for_global_fallsoft_deletion(
                session, subject=target, service_secret=SECRET
            )
        async with db.sessions() as session:
            assert not (await session.scalars(select(IdentityAuthorityAlias))).all()
