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
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "20261116_01"
    async with db.sessions.begin() as s:
        s.add(User(id="migration-fixture", subject="user_migration", username="migration", display_name="Migration QA", created_at=NOW))
    async with db.engine.begin() as connection:
        await connection.run_sync(upgrade)
    async with db.sessions() as s:
        assert (await s.execute(select(User.id))).scalars().all() == ["migration-fixture"]


async def test_deletion_migration_preserves_existing_user_data(db):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def initial(sync):
            config.attributes["connection"] = sync
            command.upgrade(config, "20261025_01")
        await connection.run_sync(initial)
    async with db.engine.begin() as connection:
        # Insert using the historical schema, not the current ORM (which now
        # contains fields added by later migrations).
        await connection.execute(text("INSERT INTO users (id, subject, username, display_name, created_at, deleted) "
            "VALUES (:id, :subject, :username, :name, :now, false)"),
            {"id":"existing-account", "subject":"user_existing", "username":"existing", "name":"Existing QA", "now":NOW})
    async with db.engine.begin() as connection:
        def upgrade(sync):
            config.attributes["connection"] = sync
            command.upgrade(config, "head")
            assert compare_metadata(MigrationContext.configure(sync), Base.metadata) == []
        await connection.run_sync(upgrade)
    async with db.sessions() as s:
        assert (await s.get(User, "existing-account")).display_name == "Existing QA"


async def test_environment_migration_rejects_ambiguous_verified_grants(db):
    import pytest
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def old(sync):
            config.attributes['connection'] = sync
            command.upgrade(config, '20261107_05')
        await connection.run_sync(old)
        await connection.execute(text("INSERT INTO users (id,subject,username,display_name,created_at,deleted) VALUES ('u','s','u','u',:now,false)"), {'now':NOW})
        await connection.execute(text("INSERT INTO entitlements (id,user_id,product,store,transaction_id,expires_at,revoked,superseded,verified_at,environment,refresh_generation,completed_generation,attempts) VALUES ('e','u','base','apple','t',:now,false,false,:now,NULL,0,0,0)"), {'now':NOW})
    with pytest.raises(RuntimeError,match='ambiguous verified store environments'):
        async with db.engine.begin() as connection:
            def upgrade(sync):
                config.attributes['connection']=sync
                command.upgrade(config,'head')
            await connection.run_sync(upgrade)


async def test_environment_migration_preserves_unknown_tombstone_and_blocks_collision_downgrade(db):
    import pytest
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def old(sync):
            config.attributes['connection']=sync
            command.upgrade(config,'20261107_05')
        await connection.run_sync(old)
        await connection.execute(text("INSERT INTO users (id,subject,username,display_name,created_at,deleted) VALUES ('u','s','u','u',:now,false)"), {'now':NOW})
        await connection.execute(text("INSERT INTO entitlements (id,user_id,product,store,transaction_id,expires_at,revoked,superseded,environment,refresh_generation,completed_generation,attempts) VALUES ('e','u','base','apple','old',:now,true,true,NULL,0,0,0)"), {'now':NOW})
        def upgrade(sync):
            config.attributes['connection']=sync
            command.upgrade(config,'head')
        await connection.run_sync(upgrade)
        assert (await connection.execute(text("SELECT environment FROM entitlements WHERE id='e'"))).scalar_one()=='Unknown'
        await connection.execute(text("INSERT INTO entitlements (id,user_id,product,store,transaction_id,expires_at,revoked,superseded,environment,refresh_generation,completed_generation,attempts) VALUES ('f','u','base','apple','same',:now,false,false,'Sandbox',0,0,0), ('g','u','base','apple','same',:now,false,false,'Production',0,0,0)"), {'now':NOW})
    with pytest.raises(RuntimeError,match='cross-environment transaction collisions'):
        async with db.engine.begin() as connection:
            def down(sync):
                config.attributes['connection']=sync
                command.downgrade(config,'20261107_05')
            await connection.run_sync(down)
