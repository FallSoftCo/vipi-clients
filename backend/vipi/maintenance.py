"""Content-free expiry task; run by the owned service timer, not request traffic."""
import asyncio
from datetime import UTC, datetime
from sqlalchemy import delete

from .config import Settings
from .db import Database, RateWindow
from .delivery import expire
from .prekeys import expire_claims


async def main():
    db = Database(Settings().database_url)
    try:
        now = datetime.now(UTC)
        async with db.sessions.begin() as session:
            await expire(session, now=now)
            await expire_claims(session, now)
            await session.execute(delete(RateWindow).where(RateWindow.window < int(now.timestamp()) // 60 - 120))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
