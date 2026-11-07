"""Durable authenticated billing events and bounded store reconciliation."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_05"
down_revision = "20261107_04"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("refresh_generation", "completed_generation"):
        op.add_column("entitlements", sa.Column(name, sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("entitlements", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    for name in ("next_attempt_at", "lease_until"):
        op.add_column("entitlements", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("entitlements", sa.Column("lease_token", sa.String(36)))
    op.create_index("ix_entitlements_next_attempt_at", "entitlements", ["next_attempt_at"])
    op.create_table("billing_notifications",
        sa.Column("store", sa.String(8), primary_key=True),
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_billing_notifications_created_at", "billing_notifications", ["created_at"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM billing_notifications")).scalar_one():
        raise RuntimeError("Preserve billing notification receipts before downgrading")
    if op.get_bind().execute(sa.text("SELECT count(*) FROM entitlements WHERE refresh_generation > completed_generation OR lease_token IS NOT NULL")).scalar_one():
        raise RuntimeError("Reconcile outstanding billing work before downgrading")
    op.drop_table("billing_notifications")
    op.drop_index("ix_entitlements_next_attempt_at", "entitlements")
    for name in ("refresh_generation", "completed_generation", "attempts", "next_attempt_at", "lease_until", "lease_token"):
        op.drop_column("entitlements", name)
