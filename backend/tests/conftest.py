from datetime import UTC, datetime
import os
from uuid import uuid4
import pytest_asyncio
from sqlalchemy import text
from vipi.db import Database, Device, User, UsageBucket

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def db(tmp_path):
    url = os.environ.get("VIPI_TEST_POSTGRES_URL")
    admin = None
    if url:
        schema = "vipi_test_" + uuid4().hex
        admin = Database(url)
        async with admin.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        value = Database(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        value = Database(f"sqlite+aiosqlite:///{tmp_path}/test.sqlite")
    await value.create_for_test()
    async with value.sessions.begin() as session:
        for name in ("alice", "bob", "eve"):
            session.add(User(id=name, subject=f"user_{name}", username=name, display_name=name, created_at=NOW))
        await session.flush()
        for name in ("alice", "bob", "eve"):
            session.add(Device(id=f"{name}-phone", user_id=name, credential_hash="x" * 64, active=True, created_at=NOW))
        session.add(UsageBucket(user_id="alice", period="2026-10", budget_nano_usd=500_000_000, reserved_nano_usd=0, spent_nano_usd=0))
    yield value
    await value.close()
    if admin:
        async with admin.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.close()
