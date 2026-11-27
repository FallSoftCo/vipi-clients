from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from .db import Reservation, UsageBucket
from .delivery import utc


class BudgetError(Exception):
    pass


async def reserve(
    session: AsyncSession,
    *,
    user_id: str,
    request_id: str,
    maximum_cost: int,
    now: datetime,
) -> Reservation:
    """Bucket must exist from entitlement provisioning. Never call provider first."""
    if maximum_cost <= 0:
        raise BudgetError("invalid_reservation")
    period = utc(now).strftime("%Y-%m")
    bucket = (
        await session.execute(
            select(UsageBucket)
            .where(UsageBucket.user_id == user_id, UsageBucket.period == period)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if bucket is None:
        raise BudgetError("allowance_unavailable")
    existing = await session.get(Reservation, request_id)
    if existing:
        # Replaying a request must never start a second provider completion.
        raise BudgetError("request_already_used")
    if (
        bucket.reserved_nano_usd + bucket.spent_nano_usd + maximum_cost
        > bucket.budget_nano_usd
    ):
        raise BudgetError("monthly_allowance_reached")
    bucket.reserved_nano_usd += maximum_cost
    item = Reservation(
        id=request_id,
        user_id=user_id,
        period=period,
        reserved_nano_usd=maximum_cost,
        created_at=utc(now),
        state="reserved",
    )
    session.add(item)
    await session.flush()
    return item


async def settle(
    session: AsyncSession, *, request_id: str, actual_cost: int | None
) -> None:
    item = await session.get(Reservation, request_id)
    if item is None:
        raise BudgetError("unknown_request")
    # Match the reservation path's lock order; reload after taking the bucket lock.
    bucket = (
        await session.execute(
            select(UsageBucket)
            .where(
                UsageBucket.user_id == item.user_id, UsageBucket.period == item.period
            )
            .with_for_update()
        )
    ).scalar_one()
    await session.refresh(item)
    if item.state not in ("reserved", "uncertain"):
        return
    if actual_cost is None:
        # Timeout/connection loss is not proof the provider spent nothing.
        item.state = "uncertain"
        return
    if actual_cost < 0:
        raise BudgetError("invalid_actual_cost")
    bucket.reserved_nano_usd -= item.reserved_nano_usd
    bucket.spent_nano_usd += actual_cost
    item.actual_nano_usd, item.state = actual_cost, "settled"
    # Record overspend accurately; subsequent reservations will be rejected.


def estimate_maximum_cost(
    input_bytes: int, output_token_limit: int, *, input_rate: int, output_rate: int
) -> int:
    if min(input_bytes, output_token_limit, input_rate, output_rate) < 0:
        raise BudgetError("invalid_price_inputs")
    # UTF-8 bytes plus framing is deliberately conservative before provider usage.
    return (input_bytes + 256) * input_rate + output_token_limit * output_rate
