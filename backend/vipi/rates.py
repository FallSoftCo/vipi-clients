from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import RateWindow
from .delivery import DeliveryError


async def consume(
    session, *, subject: str, scope: str, now: float, limit: int, seconds: int = 60
):
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(RateWindow).values(
        subject=subject, scope=scope, window=int(now) // seconds, count=1
    )
    statement = statement.on_conflict_do_update(
        index_elements=[RateWindow.subject, RateWindow.scope, RateWindow.window],
        set_={"count": RateWindow.count + 1},
        where=RateWindow.count < limit,
    ).returning(RateWindow.count)
    if (await session.execute(statement)).scalar_one_or_none() is None:
        raise DeliveryError("too_many_requests", 429)
