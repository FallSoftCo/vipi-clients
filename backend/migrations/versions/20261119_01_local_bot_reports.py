"""Explicit reports of local replies, independent of cloud reservations."""
from alembic import op
import sqlalchemy as sa

revision = "20261119_01"
down_revision = "20261117_05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("local_bot_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_local_bot_reports_user_id", "local_bot_reports", ["user_id"])
    op.create_index("ix_local_bot_reports_expires_at", "local_bot_reports", ["expires_at"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM local_bot_reports")).scalar_one():
        raise RuntimeError("Preserve pending reports before downgrading")
    op.drop_table("local_bot_reports")
