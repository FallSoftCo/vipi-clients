"""Durable account deletion and identity-provider cleanup receipts."""
from alembic import op
import sqlalchemy as sa

revision = "20261025_02"
down_revision = "20261025_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_deletions",
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("receipt_hash", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True))
    op.create_index("ix_account_deletions_next_attempt_at", "account_deletions", ["next_attempt_at"])


def downgrade():
    # Pending identity cleanup cannot safely be discarded as a routine rollback.
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM account_deletions")).scalar_one()
    if count:
        raise RuntimeError("Retain account deletion receipts before downgrading")
    op.drop_table("account_deletions")
