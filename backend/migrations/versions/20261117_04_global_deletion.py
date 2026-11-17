"""Atomic shared-account erasure receipts and minimal re-provision holds."""
from alembic import op
import sqlalchemy as sa

revision = "20261117_04"
down_revision = "20261117_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("global_deletion_holds",
        sa.Column("subject_hash", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("global_deletion_receipts",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("central_subject_hash", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.String(32), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_global_deletion_receipts_finished_at", "global_deletion_receipts", ["finished_at"])


def downgrade():
    db = op.get_bind()
    if any(db.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one()
           for table in ("global_deletion_holds", "global_deletion_receipts")):
        raise RuntimeError("Global deletion holds/receipts must survive; unsafe downgrade")
    op.drop_table("global_deletion_receipts")
    op.drop_table("global_deletion_holds")
