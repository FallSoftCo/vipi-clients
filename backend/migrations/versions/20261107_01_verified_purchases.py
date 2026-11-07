"""Provider-bound subscription refresh state; existing grants fail closed until verified."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_01"
down_revision = "20261025_02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("entitlements", sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("entitlements", sa.Column("provider_reference", sa.LargeBinary(), nullable=True))
    op.add_column("entitlements", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("entitlements", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("entitlements", sa.Column("environment", sa.String(16), nullable=True))
    op.create_table("bot_pools",
        sa.Column("period", sa.String(7), primary_key=True),
        sa.Column("budget_nano_usd", sa.BigInteger(), nullable=False),
        sa.Column("reserved_nano_usd", sa.BigInteger(), nullable=False),
        sa.Column("spent_nano_usd", sa.BigInteger(), nullable=False))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM bot_pools")).scalar_one():
        raise RuntimeError("Preserve bot spend accounting before downgrading")
    if op.get_bind().execute(sa.text("SELECT count(*) FROM entitlements WHERE verified_at IS NOT NULL")).scalar_one():
        raise RuntimeError("Preserve verified purchase bindings before downgrading")
    for column in ("environment", "trial_ends_at", "verified_at", "provider_reference", "superseded"):
        op.drop_column("entitlements", column)
    op.drop_table("bot_pools")
