from pathlib import Path
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select, text

from conftest import NOW
from vipi.db import Base, User


async def test_initial_migration_matches_models_and_preserves_data_on_repeat(db):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    async with db.engine.begin() as connection:
        # The db fixture is a unique disposable schema, never an application DB.
        await connection.run_sync(Base.metadata.drop_all)
        def upgrade(sync):
            config.attributes["connection"] = sync
            command.upgrade(config, "head")
            assert compare_metadata(MigrationContext.configure(sync), Base.metadata) == []
        await connection.run_sync(upgrade)
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "20261025_01"
    async with db.sessions.begin() as s:
        s.add(User(id="migration-fixture", subject="user_migration", username="migration", display_name="Migration QA", created_at=NOW))
    async with db.engine.begin() as connection:
        await connection.run_sync(upgrade)
    async with db.sessions() as s:
        assert (await s.execute(select(User.id))).scalars().all() == ["migration-fixture"]
