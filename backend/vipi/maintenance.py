"""Content-free expiry task; run by the owned service timer, not request traffic."""
import asyncio
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete

from .config import Settings
from .db import BillingNotification, BotReport, LocalBotReport, Database, RateWindow, UserReport
from .delivery import expire
from .prekeys import expire_claims
from .deletion import expire_deletion_receipts


async def main():
    settings = Settings()
    if settings.recovery_hold:
        # Do not construct database/provider clients or dispatch/expire records.
        return
    db = Database(settings.database_url)
    try:
        await db.check_admission()
    except BaseException:
        await db.close()
        raise
    try:
        now = datetime.now(UTC)
        async with db.sessions.begin() as session:
            await expire(session, now=now)
            from .groups import expire as expire_groups
            await expire_groups(session, now=now)
            await expire_claims(session, now)
            await session.execute(delete(RateWindow).where(RateWindow.window < int(now.timestamp()) // 60 - 120))
            await expire_deletion_receipts(session, now)
            await session.execute(delete(BotReport).where(BotReport.expires_at <= now))
            await session.execute(delete(LocalBotReport).where(LocalBotReport.expires_at <= now))
            await session.execute(delete(UserReport).where(UserReport.expires_at <= now))
            await session.execute(delete(BillingNotification).where(BillingNotification.created_at < now - timedelta(days=30)))
        # Vipi deletion completes in its own transaction. Never drain historical
        # provider-user jobs using whichever shared identity environment is live.

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
