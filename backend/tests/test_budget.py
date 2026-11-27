from uuid import uuid4
import pytest
from vipi.budget import BudgetError, reserve, settle, estimate_maximum_cost
from vipi.db import UsageBucket
from conftest import NOW


async def test_reserve_before_spend_and_block_excess(db):
    request_id = str(uuid4())
    async with db.sessions.begin() as s:
        await reserve(
            s, user_id="alice", request_id=request_id, maximum_cost=450_000_000, now=NOW
        )
    async with db.sessions.begin() as s:
        with pytest.raises(BudgetError, match="monthly_allowance_reached"):
            await reserve(
                s,
                user_id="alice",
                request_id=str(uuid4()),
                maximum_cost=50_000_001,
                now=NOW,
            )
        with pytest.raises(BudgetError, match="request_already_used"):
            await reserve(
                s, user_id="alice", request_id=request_id, maximum_cost=1, now=NOW
            )
        await settle(s, request_id=request_id, actual_cost=100_000_000)
    async with db.sessions.begin() as s:
        bucket = await s.get(UsageBucket, ("alice", "2026-10"))
        assert bucket.reserved_nano_usd == 0 and bucket.spent_nano_usd == 100_000_000
        await settle(s, request_id=request_id, actual_cost=100_000_000)
        assert bucket.spent_nano_usd == 100_000_000
        await reserve(
            s,
            user_id="alice",
            request_id=str(uuid4()),
            maximum_cost=400_000_000,
            now=NOW,
        )


async def test_unknown_provider_result_retains_reservation_until_reconciled(db):
    request_id = str(uuid4())
    async with db.sessions.begin() as s:
        await reserve(
            s, user_id="alice", request_id=request_id, maximum_cost=500_000_000, now=NOW
        )
    async with db.sessions.begin() as s:
        await settle(s, request_id=request_id, actual_cost=None)
    async with db.sessions.begin() as s:
        with pytest.raises(BudgetError, match="monthly_allowance_reached"):
            await reserve(
                s, user_id="alice", request_id=str(uuid4()), maximum_cost=1, now=NOW
            )
        await settle(s, request_id=request_id, actual_cost=10)
    async with db.sessions.begin() as s:
        bucket = await s.get(UsageBucket, ("alice", "2026-10"))
        assert bucket.reserved_nano_usd == 0 and bucket.spent_nano_usd == 10


async def test_cost_above_reservation_is_not_hidden(db):
    request_id = str(uuid4())
    async with db.sessions.begin() as s:
        await reserve(
            s, user_id="alice", request_id=request_id, maximum_cost=1, now=NOW
        )
    async with db.sessions.begin() as s:
        await settle(s, request_id=request_id, actual_cost=500_000_001)
    async with db.sessions.begin() as s:
        with pytest.raises(BudgetError, match="monthly_allowance_reached"):
            await reserve(
                s, user_id="alice", request_id=str(uuid4()), maximum_cost=1, now=NOW
            )


def test_reserve_estimate_includes_context_output_and_framing():
    assert estimate_maximum_cost(2000, 200, input_rate=300, output_rate=1200) == 916800
    with pytest.raises(BudgetError):
        estimate_maximum_cost(-1, 200, input_rate=300, output_rate=1200)
