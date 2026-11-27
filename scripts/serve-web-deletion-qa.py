#!/usr/bin/env python3
"""Loopback-only synthetic browser qualification; never uses real credentials."""

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import socket
import sys

import httpx
from sqlalchemy import select
import uvicorn

ROOT = Path("/aosp/development/vipi")
sys.path.insert(0, str(ROOT / "backend"))
from vipi.api import create_app
from vipi.auth import Principal
from vipi.config import Settings
from vipi.db import Database, User
from vipi.deletion import process_deletions

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("work", type=Path)
parser.add_argument("--complete", action="store_true")
args = parser.parse_args()
assert socket.gethostname() == "ozzz-aosp"
config = json.loads((args.work / "fixture.json").read_text())
assert config["origin"].startswith("https://127.0.0.1:")
db = Database("sqlite+aiosqlite:///" + str(args.work / "fixture.sqlite"))


class Identity:
    async def verify(self, token):
        assert token == "synthetic-browser-token"
        return Principal(
            "user_browser_fixture",
            "session_browser_fixture",
            int(datetime.now(UTC).timestamp()),
        )


async def provider(request):
    assert str(request.url) == "https://api.workos.com/user_management/authenticate"
    return httpx.Response(
        200,
        json={
            "access_token": "synthetic-browser-token",
            "user": {
                "id": "user_browser_fixture",
                "email": "browser-fixture@vipi.test",
            },
        },
    )


async def prepare():
    await db.create_for_test()
    async with db.sessions.begin() as session:
        if (
            not await session.scalar(select(User))
            and not (args.work / "initialized").exists()
        ):
            session.add(
                User(
                    id=config["account"],
                    subject="user_browser_fixture",
                    username="mika",
                    display_name="Mika",
                    created_at=datetime.now(UTC),
                )
            )
    (args.work / "initialized").touch()


async def complete():
    class Provider:
        async def delete(self, subject):
            assert subject == "user_browser_fixture"

    counts = await process_deletions(db, Provider(), now=datetime.now(UTC))
    assert counts["finished"] == 1
    await db.close()


if args.complete:
    asyncio.run(complete())
else:
    asyncio.run(prepare())
    app = create_app(
        Settings(
            database_url=str(db.engine.url),
            workos_client_id="client_browserfixture",
            workos_issuer="https://api.workos.com",
            service_secret=config["secret"],
            account_deletion_enabled=True,
            workos_dedicated_user_pool=True,
            workos_api_key="synthetic-no-network",
            deletion_web_origin=config["origin"],
        ),
        database=db,
        verifier=Identity(),
        web_provider_transport=httpx.MockTransport(provider),
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=config["port"],
        ssl_keyfile=str(args.work / "key.pem"),
        ssl_certfile=str(args.work / "cert.pem"),
        access_log=False,
        log_level="error",
    )
