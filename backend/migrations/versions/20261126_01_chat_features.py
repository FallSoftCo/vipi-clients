"""Bind optional chat features to an installed device and flag silent opaque envelopes."""

from alembic import op
import sqlalchemy as sa

revision = "20261126_01"
down_revision = "20261121_04"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("chat_features_v1_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "pending_messages",
        sa.Column("required_chat_features_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade():
    # Removing the flag could expose unconsumed control envelopes to old clients.
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pending_messages WHERE required_chat_features_version <> 0 LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Retained chat feature envelopes require the compatible schema")
    op.drop_column("pending_messages", "required_chat_features_version")
    op.drop_column("devices", "chat_features_v1_until")
