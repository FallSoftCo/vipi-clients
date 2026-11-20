"""Durable exact group admission outcomes and actor-bound cancellation fences.

Legacy admitted results remain NULL: never fabricate a prior roster snapshot.
This migration belongs only to the disabled Groups upgrade branch.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261120_01"
down_revision = "20261119_02"
branch_labels = None
depends_on = None


def upgrade():
    for column in (sa.Column("expected_epoch",sa.Integer(),nullable=True),
                   sa.Column("original_device_id",sa.String(36),nullable=True),
                   sa.Column("admitted_result",sa.LargeBinary(),nullable=True)):
        op.add_column("group_operations",column)
    op.add_column("group_messages",sa.Column("admitted_result",sa.LargeBinary(),nullable=True))
    op.create_table("group_cancellations",
        sa.Column("group_id",sa.String(36),sa.ForeignKey("chat_groups.id"),primary_key=True),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),primary_key=True),
        sa.Column("request_id",sa.String(36),primary_key=True),
        sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("expected_epoch",sa.Integer(),nullable=False),
        sa.Column("original_device_id",sa.String(36),nullable=False),
        sa.Column("control_expires_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))


def downgrade():
    raise RuntimeError("Durable group cancellation fences cannot be downgraded safely")
