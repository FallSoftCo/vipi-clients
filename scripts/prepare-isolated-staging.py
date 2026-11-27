#!/usr/bin/env python3
"""Prepare only tagged test identities in Vipi's dedicated free staging pool.

Secrets are written to the private controller directory, never stdout/source.
Reconciles uncertain creates by exact email AND our recorded metadata tag.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
from uuid import uuid4
import httpx

ROOT = Path("/aosp/development/vipi")
PRIVATE = Path("/home/aosp/.local/state/vipi/workos-isolated")
CLIENT = "client_01M5S2CDSQ8F7FEX26G3CY9VS1"
ENVIRONMENT = "environment_01M5S2CDCTMYJ46EBGXYWS5KBC"


async def main(revision):
    assert socket.gethostname() == "ozzz-aosp"
    file = PRIVATE / f"cohort-{revision}.json"
    key = (PRIVATE / "api-key").read_text().strip()
    assert key.startswith("sk_test_")
    if file.exists():
        value = json.loads(file.read_text())
        assert value["client_id"] == CLIENT and value["environment"] == ENVIRONMENT
    else:
        tag = "vipi-isolated-" + uuid4().hex
        value = {
            "client_id": CLIENT,
            "environment": ENVIRONMENT,
            "run": str(uuid4()),
            "tag": tag,
            "users": {},
        }
        for role in ("android", "ios", "web"):
            value["users"][role] = {
                "email": tag + "-" + role + "@fallsoft.co",
                "password": secrets.token_urlsafe(32) + "aA1!",
            }

    def save():
        tmp = file.with_suffix(".tmp")
        tmp.write_text(json.dumps(value))
        tmp.chmod(0o600)
        tmp.replace(file)

    save()
    async with httpx.AsyncClient(
        base_url="https://api.workos.com",
        headers={"Authorization": "Bearer " + key},
        timeout=20,
        follow_redirects=False,
    ) as api:
        for role, user in value["users"].items():
            found = await api.get(
                "/user_management/users", params={"email": user["email"], "limit": 2}
            )
            assert found.status_code == 200, "fixture lookup failed"
            matches = found.json()["data"]
            assert len(matches) <= 1, "ambiguous fixture"
            if matches:
                record = matches[0]
                assert (
                    record["email"] == user["email"]
                    and record.get("metadata", {}).get("vipi_qa_run") == value["tag"]
                )
            else:
                assert "subject" not in user, (
                    "previously prepared fixture was removed; use a new revision"
                )
                response = await api.post(
                    "/user_management/users",
                    json={
                        "email": user["email"],
                        "password": user["password"],
                        "email_verified": True,
                        "metadata": {"vipi_qa_run": value["tag"], "vipi_qa_role": role},
                    },
                )
                assert response.status_code in (200, 201), "fixture creation failed"
                record = response.json()
            if "subject" in user:
                assert user["subject"] == record["id"]
            user["subject"] = record["id"]
            save()
            authenticated = await api.post(
                "/user_management/authenticate",
                json={
                    "client_id": CLIENT,
                    "client_secret": key,
                    "grant_type": "password",
                    "email": user["email"],
                    "password": user["password"],
                },
            )
            assert authenticated.status_code == 200, "fixture authentication failed"
            tokens = authenticated.json()
            assert tokens["user"]["id"] == user["subject"]
            user["session"] = {
                "userID": user["subject"],
                "accessToken": tokens["access_token"],
                "refreshToken": tokens["refresh_token"],
            }
            save()
            (PRIVATE / f"qa-{role}-{revision}.json").write_text(
                json.dumps(user["session"])
            )
        cutover = {
            "client_id": CLIENT,
            "workos_api_key": key,
            "subjects": [u["subject"] for u in value["users"].values()],
            "environment_id": ENVIRONMENT,
            "cohort_run": value["run"],
        }
        (PRIVATE / f"cutover-{revision}.json").write_text(json.dumps(cutover))
    receipt = {
        "client_id": CLIENT,
        "environment": ENVIRONMENT,
        "cohort_run": value["run"],
        "roles": list(value["users"]),
        "subject_count": len(value["users"]),
        "real_password_authentication": True,
        "live_api_changed": False,
    }
    output = ROOT / f"artifacts/isolated-staging-cohort-{revision}.json"
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"receipt": str(output), "subject_count": len(value["users"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    args = parser.parse_args()
    assert args.revision.isdigit() and len(args.revision) == 3
    os.umask(0o077)
    asyncio.run(main(args.revision))
