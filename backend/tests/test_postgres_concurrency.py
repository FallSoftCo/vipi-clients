import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_delivery import message
from vipi.accounts import register_device
from vipi.budget import BudgetError, reserve
from vipi.db import Device, PendingMessage, UsageBucket
from vipi.delivery import DeliveryError, accept


@pytest.fixture(autouse=True)
def require_postgres(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Requires isolated real PostgreSQL; SQLite cannot prove row locking")


async def test_parallel_queue_admission_never_exceeds_cap(db):
    async def send():
        try:
            async with db.sessions.begin() as s:
                await accept(s, message(), now=NOW, max_pending=5)
            return "accepted"
        except DeliveryError as error:
            return error.code
    results = await asyncio.gather(*(send() for _ in range(25)))
    assert results.count("accepted") == 5
    assert results.count("recipient_queue_full") == 20
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(PendingMessage))).scalar_one() == 5


async def test_parallel_retries_accept_one_row(db):
    envelope = message()
    async def send():
        async with db.sessions.begin() as s:
            return (await accept(s, envelope, now=NOW)).id
    assert set(await asyncio.gather(*(send() for _ in range(20)))) == {envelope.id}
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(PendingMessage))).scalar_one() == 1


async def test_concurrent_budget_reservations_cannot_overspend(db):
    async def spend():
        try:
            async with db.sessions.begin() as s:
                await reserve(s, user_id="alice", request_id=str(uuid4()), maximum_cost=100_000_000, now=NOW)
            return "accepted"
        except BudgetError as error:
            return str(error)
    results = await asyncio.gather(*(spend() for _ in range(20)))
    assert results.count("accepted") == 5
    async with db.sessions() as s:
        assert (await s.get(UsageBucket, ("alice", "2026-10"))).reserved_nano_usd == 500_000_000


async def test_racing_replacement_and_delivery_leaves_no_old_identity_backlog(db):
    async def replace():
        async with db.sessions.begin() as s:
            await register_device(s, user_id="bob", device_id="bob-new", secret="a" * 43,
                replace_active=True, service_secret="b" * 43, now=NOW)
    async def send():
        try:
            async with db.sessions.begin() as s:
                await accept(s, message(), now=NOW)
        except DeliveryError as error:
            assert error.code == "recipient_identity_changed"
    await asyncio.gather(replace(), *(send() for _ in range(15)))
    async with db.sessions() as s:
        assert not (await s.get(Device, "bob-phone")).active
        assert (await s.get(Device, "bob-new")).active
        items = (await s.execute(select(PendingMessage))).scalars().all()
        assert all(item.ciphertext is None and item.state == "identity_changed" for item in items)
