"""A relay that already offers either upgrade can add the other in place."""

from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select, text

from conftest import NOW
from vipi.db import Base, ChatGroup, MediaBlob, User


@pytest.mark.parametrize(
    ("start", "table", "feature_values"),
    [
        (
            "20261121_02",
            ChatGroup.__table__,
            {
                "id": "existing-group",
                "creator_id": "existing-user",
                "creation_fingerprint": "3" * 64,
                "title": "Family",
                "epoch": 7,
                "state": "active",
                "created_at": NOW,
            },
        ),
        (
            "20261120_01_media",
            MediaBlob.__table__,
            {
                "id": "existing-attachment",
                "owner_id": "existing-user",
                "owner_device_id": "existing-device",
                "ciphertext_bytes": 1024,
                "ciphertext_sha256": "4" * 64,
                "state": "ready",
                "created_at": NOW,
                "expires_at": NOW + timedelta(hours=72),
            },
        ),
    ],
    ids=["groups-first", "media-first"],
)
async def test_upgrade_keeps_existing_feature_data(db, start, table, feature_values):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

        def migrate(sync, revision):
            config.attributes["connection"] = sync
            command.upgrade(config, revision)

        await conn.run_sync(migrate, start)
        await conn.execute(
            User.__table__.insert().values(
                id="existing-user",
                subject="existing-subject",
                username="family",
                display_name="Family",
                created_at=NOW,
            )
        )
        await conn.execute(table.insert().values(**feature_values))
        query = select(table).where(table.c.id == feature_values["id"])
        before = (await conn.execute(query)).mappings().one()
        await conn.run_sync(migrate, "head")
        after = (await conn.execute(query)).mappings().one()
        assert dict(after) == dict(before)
        assert (
            await conn.scalars(text("SELECT version_num FROM alembic_version"))
        ).all() == ["20261126_01"]
        assert (
            await conn.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync), Base.metadata
                )
            )
            == []
        )
