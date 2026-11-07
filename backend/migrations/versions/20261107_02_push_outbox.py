"""Content-free, coalesced push delivery for active registered devices."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_02"
down_revision = "20261107_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("push_tokens",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("provider", sa.String(8), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("token", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "environment", "fingerprint"))
    op.create_table("push_outbox",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_push_outbox_next_attempt_at", "push_outbox", ["next_attempt_at"])


def downgrade():
    op.drop_table("push_outbox")
    op.drop_table("push_tokens")
