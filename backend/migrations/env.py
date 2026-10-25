import asyncio
import os

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from vipi.db import Base

config = context.config


def run(connection):
    if os.environ.get("VIPI_MIGRATION_ROLE"):
        if os.environ["VIPI_MIGRATION_ROLE"] != "vipi_owner":
            raise ValueError("Invalid migration role")
        connection.execute(text("SET ROLE vipi_owner"))
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(os.environ["VIPI_DATABASE_URL"], poolclass=pool.NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Use an explicit database connection for Vipi migrations")
elif connection := config.attributes.get("connection"):
    run(connection)
else:
    asyncio.run(online())
