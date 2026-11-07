"""Consented private reports and operator-reviewed account restrictions."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_04"
down_revision = "20261107_03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("user_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reported_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("decision", sa.String(16)),
        sa.Column("reviewer", sa.String(128)))
    for name in ("user_id", "reported_user_id", "expires_at"):
        op.create_index("ix_user_reports_" + name, "user_reports", [name])
    op.create_table("moderation_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_moderation_actions_user_id", "moderation_actions", ["user_id"])


def downgrade():
    for table in ("user_reports", "moderation_actions"):
        if op.get_bind().execute(sa.text("SELECT count(*) FROM " + table)).scalar_one():
            raise RuntimeError("Preserve moderation records before downgrading")
    if op.get_bind().execute(sa.text("SELECT count(*) FROM users WHERE suspended")).scalar_one():
        raise RuntimeError("Do not silently lift account restrictions")
    op.drop_table("moderation_actions")
    op.drop_table("user_reports")
    op.drop_column("users", "suspended")
