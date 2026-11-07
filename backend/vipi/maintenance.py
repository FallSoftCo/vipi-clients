"""Content-free expiry task; run by the owned service timer, not request traffic."""
import asyncio
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete

from .config import Settings
from .db import BillingNotification, BotReport, Database, RateWindow, UserReport
from .delivery import expire
from .prekeys import expire_claims
from .deletion import WorkOSUserDeleter, expire_deletion_receipts, process_deletions


async def main():
    settings = Settings()
    db = Database(settings.database_url)
    try:
        now = datetime.now(UTC)
        async with db.sessions.begin() as session:
            await expire(session, now=now)
            await expire_claims(session, now)
            await session.execute(delete(RateWindow).where(RateWindow.window < int(now.timestamp()) // 60 - 120))
            await expire_deletion_receipts(session, now)
            await session.execute(delete(BotReport).where(BotReport.expires_at <= now))
            await session.execute(delete(UserReport).where(UserReport.expires_at <= now))
            await session.execute(delete(BillingNotification).where(BillingNotification.created_at < now - timedelta(days=30)))
        if settings.account_deletion_enabled:
            deleter = WorkOSUserDeleter(settings)
            try:
                await process_deletions(db, deleter, now=now)
            finally:
                await deleter.close()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
