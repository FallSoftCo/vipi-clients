"""A bounded systemd invocation; store outages cannot block relay requests."""
import asyncio
import json
import time
from datetime import UTC, datetime

from .config import Settings
from .db import Database
from .store_providers import providers_for
from .subscriptions import Subscriptions


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
    providers = providers_for(settings)
    service = Subscriptions(settings, db, providers, lambda: datetime.now(UTC))
    started, attempted = time.monotonic(), 0
    try:
        while attempted < 128 and time.monotonic() - started < 45:
            # Each worker owns a database lease. Other invocations and API
            # purchase sync cannot silently replace a newer observation.
            results = await asyncio.gather(*(service.reconcile_one() for _ in range(4)))
            attempted += sum(results)
            if not any(results):
                break
        print(json.dumps({"reconciliations_attempted": attempted, "duration_seconds": round(time.monotonic() - started, 3)}))
    finally:
        for provider in providers.values():
            await provider.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
