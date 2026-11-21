"""Durable exact group admission outcomes and actor-bound cancellation fences.

Legacy admitted results remain NULL: never fabricate a prior roster snapshot.
This migration belongs only to the disabled Groups upgrade branch.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_02"
down_revision = "20261121_01"
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
    op.create_index("ix_group_cancellations_actor_id","group_cancellations",["actor_id"])


def downgrade():
    bind=op.get_bind()
    if (bind.execute(sa.text("SELECT count(*) FROM group_cancellations")).scalar_one() or
        bind.execute(sa.text("SELECT count(*) FROM group_operations WHERE admitted_result IS NOT NULL")).scalar_one() or
        bind.execute(sa.text("SELECT count(*) FROM group_messages WHERE admitted_result IS NOT NULL")).scalar_one()):
        raise RuntimeError("Preserve durable group recovery metadata before downgrading")
    op.drop_table("group_cancellations")
    op.drop_column("group_messages","admitted_result")
    for field in ("admitted_result","original_device_id","expected_epoch"):
        op.drop_column("group_operations",field)
