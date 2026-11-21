"""Store one optional response per account and survey."""
from alembic import op
import sqlalchemy as sa

revision = "20261121_03"
down_revision = "20261121_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "survey_decisions",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("campaign", sa.String(48), primary_key=True),
        sa.Column("choice", sa.String(8), nullable=False),
        sa.CheckConstraint("choice IN ('yes','maybe','no','skip')", name="ck_survey_choice"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM survey_decisions LIMIT 1")).scalar():
        raise RuntimeError("Preserve existing survey decisions before downgrading")
    op.drop_table("survey_decisions")
