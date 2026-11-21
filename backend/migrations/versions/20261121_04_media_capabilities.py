"""Join survey and relay histories and track media support per installed device."""
from alembic import op
import sqlalchemy as sa

revision = "20261121_04"
down_revision = ("20261121_03", "20261121_03_relay")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("media_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("devices", "media_version")
