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
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "20261121_03"
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
        user = await s.get(User, "existing-account")
        assert user.display_name == "Existing QA"
        from vipi.delivery import utc
        from datetime import timedelta
        assert utc(user.cardless_trial_started_at) == NOW
        assert utc(user.cardless_trial_ends_at) == NOW + timedelta(days=30)
    async with db.engine.begin() as connection:
        def cycle(sync):
            config.attributes["connection"] = sync
            command.downgrade(config, "20261116_01")
            command.upgrade(config, "head")
        await connection.run_sync(cycle)
    async with db.sessions() as s:
        user = await s.get(User, "existing-account")
        assert utc(user.cardless_trial_started_at) == NOW
        assert utc(user.cardless_trial_ends_at) == NOW + timedelta(days=30)


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


async def test_staging_lifespan_readiness_tracks_real_postgres_alembic_head(db):
    import httpx
    import pytest
    from test_api import TestVerifier
    from vipi.api import create_app
    from vipi.config import Settings
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('requires real PostgreSQL event listener and migrations')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def upgrade(sync):
            config.attributes['connection'] = sync
            command.upgrade(config, 'head')
        await connection.run_sync(upgrade)
    options=Settings(database_url=db.engine.url.render_as_string(hide_password=False),
        workos_client_id='client_fixture',workos_issuer='https://api.workos.com',service_secret='x'*43,
        environment='staging',allowed_subjects=frozenset({'user_test'}))
    app=create_app(options,database=db,verifier=TestVerifier(),store_providers={})
    async with app.router.lifespan_context(app):
        assert app.state.events.ready.is_set()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://vipi.test') as client:
            response=await client.get('/health/ready')
            assert response.status_code==200 and response.json()=={'status':'ok'}
            app.state.events.ready.clear()
            response=await client.get('/health/ready')
            assert response.status_code==503 and response.json()=={'status':'events_unavailable'}
            app.state.events.ready.set()
            async with db.engine.begin() as connection:
                await connection.execute(text("UPDATE alembic_version SET version_num='20261107_05'"))
            response=await client.get('/health/ready')
            assert response.status_code==503 and response.json()=={'status':'schema_unavailable'}
            async with db.engine.begin() as connection:
                await connection.execute(text("UPDATE alembic_version SET version_num='20261116_01'"))


async def test_vipi_only_deletion_migration_refuses_losing_security_or_eligibility_state(db):
    import pytest
    from vipi.db import VipiTrialEligibility
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def upgrade(sync):
            config.attributes['connection'] = sync
            command.upgrade(config, 'head')
        await connection.run_sync(upgrade)
    async with db.sessions.begin() as session:
        session.add(VipiTrialEligibility(subject_hash='e'*64, started_at=NOW, ends_at=NOW))
    with pytest.raises(RuntimeError, match='unsafe downgrade'):
        async with db.engine.begin() as connection:
            def down(sync):
                config.attributes['connection'] = sync
                command.downgrade(config, '20261117_01')
            await connection.run_sync(down)
    async with db.sessions() as session:
        assert await session.get(VipiTrialEligibility, 'e'*64)


async def test_billing_binding_migration_cycle_and_refuse_loss(db):
    import pytest
    from vipi.db import BillingAccountBinding
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def upgrade(sync):
            config.attributes['connection'] = sync
            # This historical refusal is specifically at the billing migration.
            # SQLite DDL from a newer downgrade may survive a later refusal.
            command.upgrade(config, '20261117_05')
        await connection.run_sync(upgrade)
    async with db.sessions.begin() as session:
        session.add(BillingAccountBinding(store='apple', binding_hash='b'*64, owner_hash='a'*64))
    with pytest.raises(RuntimeError, match='unsafe downgrade'):
        async with db.engine.begin() as connection:
            def down(sync):
                config.attributes['connection'] = sync
                command.downgrade(config, '20261117_04')
            await connection.run_sync(down)
    async with db.sessions.begin() as session:
        row = await session.get(BillingAccountBinding, ('apple','b'*64))
        assert row.owner_hash == 'a'*64
        await session.delete(row)
    async with db.engine.begin() as connection:
        def cycle(sync):
            config.attributes['connection'] = sync
            command.downgrade(config, '20261117_04')
            command.upgrade(config, 'head')
            assert compare_metadata(MigrationContext.configure(sync), Base.metadata) == []
        await connection.run_sync(cycle)


async def test_identity_alias_migration_preserves_historical_links_and_refuses_loss(db):
    import pytest
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def historical(sync):
            config.attributes["connection"] = sync
            command.upgrade(config, "20261119_01")
        await connection.run_sync(historical)
        await connection.execute(text("INSERT INTO vipi_trial_eligibility_links (source_hash,target_hash) VALUES (:source,:target)"), {"source":"a"*64,"target":"b"*64})
    async with db.engine.begin() as connection:
        def upgrade(sync):
            config.attributes["connection"] = sync
            command.upgrade(config, "head")
            assert compare_metadata(MigrationContext.configure(sync), Base.metadata) == []
        await connection.run_sync(upgrade)
        assert (await connection.execute(text("SELECT source_hash,target_hash FROM identity_authority_aliases"))).all() == [("a"*64,"b"*64)]
        await connection.run_sync(upgrade)
    with pytest.raises(RuntimeError, match="Identity aliases must be preserved"):
        async with db.engine.begin() as connection:
            def downgrade(sync):
                config.attributes["connection"] = sync
                command.downgrade(config, "20261119_01")
            await connection.run_sync(downgrade)


async def test_group_migration_refuses_losing_membership_authority(db):
    import pytest
    from vipi.db import ChatGroup
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def upgrade(sync):
            config.attributes["connection"] = sync
            command.upgrade(config,"head")
        await connection.run_sync(upgrade)
    async with db.sessions.begin() as session:
        session.add(ChatGroup(id="group-preserve",creator_id=None,creation_fingerprint="f"*64,
            title="Retained group",epoch=1,state="closed",created_at=NOW))
    with pytest.raises(RuntimeError,match="Preserve group authority"):
        async with db.engine.begin() as connection:
            def downgrade(sync):
                config.attributes["connection"] = sync
                command.downgrade(config,"20261119_01")
            await connection.run_sync(downgrade)
    async with db.sessions() as session:
        assert (await session.get(ChatGroup,"group-preserve")).title == "Retained group"


async def test_group_recovery_migration_keeps_legacy_outcome_unknown_and_guards_live_fences(db):
    import pytest
    from vipi.db import GroupCancellation
    config=Config(str(Path(__file__).resolve().parents[1]/"alembic.ini"))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def old(sync):
            config.attributes['connection']=sync;command.upgrade(config,'20261121_01')
        await connection.run_sync(old)
        await connection.execute(text("INSERT INTO users (id,subject,username,display_name,created_at,deleted,cardless_trial_started_at,cardless_trial_ends_at) VALUES ('u','s','u','u',:now,false,:now,:now)"),{'now':NOW})
        await connection.execute(text("INSERT INTO chat_groups (id,creator_id,creation_fingerprint,title,epoch,state,created_at) VALUES ('g','u',:fp,'Legacy',1,'active',:now)"),{'fp':'a'*64,'now':NOW})
        await connection.execute(text("INSERT INTO group_operations (group_id,request_id,actor_id,fingerprint,created_at) VALUES ('g','r','u',:fp,:now)"),{'fp':'b'*64,'now':NOW})
        def upgrade(sync):
            config.attributes['connection']=sync;command.upgrade(config,'head')
            assert compare_metadata(MigrationContext.configure(sync),Base.metadata)==[]
        await connection.run_sync(upgrade)
        values=(await connection.execute(text("SELECT actor_id,admitted_result,original_device_id,expected_epoch FROM group_operations WHERE group_id='g'"))).one()
        assert tuple(values)==('u',None,None,None)
    async with db.sessions.begin() as session:
        session.add(GroupCancellation(group_id='g',actor_id='u',request_id='cancel',fingerprint='c'*64,
            expected_epoch=1,original_device_id='original-device',created_at=NOW))
    with pytest.raises(RuntimeError,match='Preserve durable group recovery'):
        async with db.engine.begin() as connection:
            def down(sync):
                config.attributes['connection']=sync;command.downgrade(config,'20261121_01')
            await connection.run_sync(down)
    async with db.sessions() as session:
        assert await session.get(GroupCancellation,('g','u','cancel'))
