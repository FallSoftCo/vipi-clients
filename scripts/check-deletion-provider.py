#!/usr/bin/env python3
"""Qualify real WorkOS deletion using only fresh, tagged Vipi staging fixtures.

No network listener. Real JWT verification and provider API; local disposable DB.
Never points at the original shared Fallible Software environment or production.
"""

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from uuid import uuid4

import httpx
from sqlalchemy import select

ROOT = Path("/aosp/development/vipi")
sys.path.insert(0, str(ROOT / "backend"))
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import AccountDeletion, Database, User
from vipi.deletion import WorkOSUserDeleter, process_deletions

CLIENT = "client_01M5S2CDSQ8F7FEX26G3CY9VS1"
ENVIRONMENT = "environment_01M5S2CDCTMYJ46EBGXYWS5KBC"
PRIVATE = Path("/home/aosp/.local/state/vipi/workos-isolated")


def require(ok, step):
    if not ok:
        raise RuntimeError(step)


async def run(revision):
    require(socket.gethostname() == "ozzz-aosp", "wrong_host")
    output = ROOT / f"artifacts/deletion-provider-{revision}.json"
    require(not output.exists(), "preserve_existing_receipt")
    work = ROOT / f".runtime/deletion-provider-{revision}"
    work.mkdir(mode=0o700)
    key = (PRIVATE / "api-key").read_text().strip()
    require(key.startswith("sk_test_"), "staging_key_required")
    receipt = {
        "environment": ENVIRONMENT,
        "client_id": CLIENT,
        "network_listener": False,
        "real_workos": True,
        "database": "isolated_SQLite",
        "cases": [],
        "passed": False,
    }
    try:
        async with httpx.AsyncClient(
            base_url="https://api.workos.com",
            headers={"Authorization": "Bearer " + key},
            timeout=20,
            follow_redirects=False,
        ) as provider:
            listing = await provider.get("/user_management/users", params={"limit": 1})
            require(
                listing.status_code == 200 and listing.json().get("data") == [],
                "dedicated_empty_staging_required",
            )
            for with_profile in (True, False):
                case = {
                    "profile_created": with_profile,
                    "passed": False,
                    "cleanup_confirmed": False,
                }
                receipt["cases"].append(case)
                tag = "vipi-delete-" + uuid4().hex
                email = tag + "@fallsoft.co"
                journal = PRIVATE / (tag + ".json")
                journal.write_text(
                    json.dumps(
                        {"email": email, "qa_run": tag, "environment": ENVIRONMENT}
                    )
                    + "\n"
                )
                journal.chmod(0o600)
                subject = None
                db = None
                app = None
                deleter = None
                try:
                    case["step"] = "create_fixture"
                    password = secrets.token_urlsafe(32) + "aA1!"
                    created = await provider.post(
                        "/user_management/users",
                        json={
                            "email": email,
                            "password": password,
                            "email_verified": True,
                            "first_name": "Vipi",
                            "last_name": "Deletion QA",
                            "metadata": {"vipi_qa_run": tag},
                        },
                    )
                    require(
                        created.status_code in (200, 201),
                        "fixture_create_http_" + str(created.status_code),
                    )
                    subject = created.json()["id"]
                    journal.write_text(
                        json.dumps(
                            {
                                "email": email,
                                "qa_run": tag,
                                "subject": subject,
                                "environment": ENVIRONMENT,
                            }
                        )
                        + "\n"
                    )
                    case["step"] = "authenticate_fixture"
                    auth = await provider.post(
                        "/user_management/authenticate",
                        json={
                            "client_id": CLIENT,
                            "client_secret": key,
                            "grant_type": "password",
                            "email": email,
                            "password": password,
                        },
                    )
                    require(
                        auth.status_code == 200,
                        "fixture_auth_http_" + str(auth.status_code),
                    )
                    tokens = auth.json()
                    require(
                        tokens["user"]["id"] == subject, "fixture_identity_mismatch"
                    )
                    settings = Settings(
                        database_url="sqlite+aiosqlite:///"
                        + str(work / (tag + ".sqlite")),
                        workos_client_id=CLIENT,
                        workos_issuer="https://api.workos.com",
                        service_secret=secrets.token_urlsafe(32),
                        environment="staging",
                        allowed_subjects=frozenset([subject]),
                        account_deletion_enabled=True,
                        workos_dedicated_user_pool=True,
                        workos_api_key=key,
                    )
                    db = Database(settings.database_url)
                    await db.create_for_test()
                    app = create_app(settings, database=db)
                    deleter = WorkOSUserDeleter(settings)
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="https://vipi.test",
                    ) as api:
                        headers = {"Authorization": "Bearer " + tokens["access_token"]}
                        case["step"] = "verify_real_jwt"
                        me = await api.get("/v1/me", headers=headers)
                        require(
                            me.status_code == 404
                            and me.json()["error"] == "profile_required",
                            "real_jwt_rejected",
                        )
                        case["real_jwt_verified"] = True
                        account = str(uuid4())
                        if with_profile:
                            profile = await api.put(
                                "/v1/me",
                                headers=headers,
                                json={
                                    "username": "deleteqa_" + secrets.token_hex(4),
                                    "display_name": "Deletion QA",
                                },
                            )
                            require(profile.status_code == 200, "profile_setup_failed")
                            account = profile.json()["id"]
                        capability = secrets.token_urlsafe(32)
                        # The native clients persist this capability in encrypted
                        # device storage. The private fixture records it before DELETE.
                        cap_path = work / "pending-capability.json"
                        cap_path.write_text(
                            json.dumps(
                                {"account_id": account, "receipt_secret": capability}
                            )
                        )
                        cap_path.chmod(0o600)
                        case["step"] = "request_deletion"
                        body = json.loads(cap_path.read_text())
                        requested = await api.request(
                            "DELETE", "/v1/me", json=body, headers=headers
                        )
                        require(
                            requested.status_code == 202
                            and requested.json()["status"] == "deletion_requested",
                            "deletion_not_accepted",
                        )
                        status_headers = {"Authorization": "Deletion " + capability}
                        url = "/v1/account-deletions/" + account
                        require(
                            (await api.get(url, headers=status_headers)).json()[
                                "status"
                            ]
                            == "deletion_requested",
                            "pending_receipt_missing",
                        )
                        case["step"] = "real_provider_cleanup"
                        counts = await process_deletions(
                            db, deleter, now=datetime.now(UTC), limit=1
                        )
                        require(
                            counts["finished"] == 1, "provider_cleanup_not_finished"
                        )
                        case["provider_user_get_status"] = (
                            await provider.get("/user_management/users/" + subject)
                        ).status_code
                        require(
                            case["provider_user_get_status"] == 404,
                            "provider_identity_still_present",
                        )
                        require(
                            (await api.get(url, headers=status_headers)).json()[
                                "status"
                            ]
                            == "deleted",
                            "completion_receipt_missing",
                        )
                        require(
                            (await api.get("/v1/me", headers=headers)).status_code
                            == 404,
                            "profile_still_present",
                        )
                        blocked = await api.put(
                            "/v1/me",
                            headers=headers,
                            json={"username": "recreate_qa", "display_name": "QA"},
                        )
                        require(
                            blocked.status_code == 409,
                            "old_access_token_recreated_profile",
                        )
                        refresh = await provider.post(
                            "/user_management/authenticate",
                            json={
                                "client_id": CLIENT,
                                "grant_type": "refresh_token",
                                "refresh_token": tokens["refresh_token"],
                            },
                        )
                        case["refresh_after_deletion_status"] = refresh.status_code
                        require(
                            refresh.status_code in (400, 401),
                            "deleted_identity_refreshed",
                        )
                        async with db.sessions() as session:
                            job = await session.get(AccountDeletion, account)
                            require(
                                job.subject is None and job.finished_at is not None,
                                "provider_identifier_retained",
                            )
                            require(
                                not list((await session.scalars(select(User))).all()),
                                "profile_rows_retained",
                            )
                        cap_path.unlink()
                        case["passed"] = True
                        case["step"] = "completed"
                finally:
                    if deleter:
                        await deleter.close()
                    if app:
                        await app.state.verifier.close()
                    if db:
                        await db.close()
                    # Resolve an uncertain create only by this run's unique email
                    # AND metadata tag; never delete a pre-existing user.
                    found = await provider.get(
                        "/user_management/users", params={"email": email, "limit": 10}
                    )
                    require(found.status_code == 200, "fixture_cleanup_lookup_failed")
                    for user in found.json().get("data", []):
                        require(
                            user["email"] == email
                            and user.get("metadata", {}).get("vipi_qa_run") == tag,
                            "fixture_cleanup_tag_mismatch",
                        )
                        removed = await provider.delete(
                            "/user_management/users/" + user["id"]
                        )
                        require(
                            removed.status_code in (200, 204, 404),
                            "fixture_cleanup_failed",
                        )
                    check = await provider.get(
                        "/user_management/users", params={"email": email, "limit": 1}
                    )
                    case["cleanup_confirmed"] = (
                        check.status_code == 200 and check.json().get("data") == []
                    )
                    if case["cleanup_confirmed"]:
                        journal.unlink()
            receipt["passed"] = all(
                c["passed"] and c["cleanup_confirmed"] for c in receipt["cases"]
            )
    except Exception as error:
        # Exception text from networking/libraries may include credentials.
        receipt["failure_type"] = type(error).__name__
        if type(error) is RuntimeError:
            receipt["failure_step"] = str(error)
    finally:
        output.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "receipt": str(output),
                    "passed": receipt["passed"],
                    "failure_step": receipt.get("failure_step"),
                }
            )
        )
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    args = parser.parse_args()
    require(
        args.revision.isdigit() and len(args.revision) == 3,
        "three_digit_revision_required",
    )
    os.umask(0o077)
    sys.exit(asyncio.run(run(args.revision)))
