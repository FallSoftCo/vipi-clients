"""User-selected bot reports with explicit bounded retention."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_03"
down_revision = "20261107_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("bot_reports",
        sa.Column("request_id", sa.String(36), sa.ForeignKey("bot_reservations.id"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("selected_reply", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_bot_reports_user_id", "bot_reports", ["user_id"])
    op.create_index("ix_bot_reports_expires_at", "bot_reports", ["expires_at"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM bot_reports")).scalar_one():
        raise RuntimeError("Preserve pending reports before downgrading")
    op.drop_table("bot_reports")
