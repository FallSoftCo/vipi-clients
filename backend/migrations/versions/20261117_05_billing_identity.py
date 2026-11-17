"""Minimal purchase ownership across app-only deletion, erased globally."""
from alembic import op
import sqlalchemy as sa

revision = "20261117_05"
down_revision = "20261117_04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("billing_account_bindings",
        sa.Column("store", sa.String(16), primary_key=True),
        sa.Column("binding_hash", sa.String(64), primary_key=True),
        sa.Column("owner_hash", sa.String(64), nullable=False))
    op.create_index("ix_billing_account_bindings_owner_hash", "billing_account_bindings", ["owner_hash"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM billing_account_bindings")).scalar_one():
        raise RuntimeError("Purchase ownership bindings must survive; unsafe downgrade")
    op.drop_table("billing_account_bindings")
