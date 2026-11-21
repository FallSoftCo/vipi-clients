"""Isolated opt-in group membership and atomic fanout metadata."""
from alembic import op
import sqlalchemy as sa

revision = "20261121_01"
down_revision = "20261119_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("chat_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), nullable=True),
        sa.Column("creation_fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("group_members",
        sa.Column("group_id", sa.String(36), sa.ForeignKey("chat_groups.id"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("joined_epoch", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])
    op.create_table("group_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("chat_groups.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invited_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("group_id", "user_id", "expires_at"):
        op.create_index("ix_group_invitations_" + column, "group_invitations", [column])
    op.create_table("group_operations",
        sa.Column("group_id", sa.String(36), sa.ForeignKey("chat_groups.id"), primary_key=True),
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_group_operations_actor_id", "group_operations", ["actor_id"])
    op.create_table("group_messages",
        sa.Column("group_id", sa.String(36), sa.ForeignKey("chat_groups.id"), primary_key=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender_device_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("envelope_ids", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_group_messages_sender_id", "group_messages", ["sender_id"])
    op.create_index("ix_group_messages_expires_at", "group_messages", ["expires_at"])
    op.add_column("pending_messages", sa.Column("group_id", sa.String(36), nullable=True))
    op.add_column("pending_messages", sa.Column("group_epoch", sa.Integer(), nullable=True))
    op.add_column("pending_messages", sa.Column("group_message_id", sa.String(36), nullable=True))
    op.add_column("pending_messages", sa.Column("group_kind", sa.String(16), nullable=True))
    op.create_index("ix_pending_messages_group_id", "pending_messages", ["group_id"])
    op.add_column("push_outbox", sa.Column("group_event", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    # Refuse to silently lose membership authority or group retry/queue context.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM chat_groups")).scalar_one():
        raise RuntimeError("Preserve group authority before downgrading")
    op.drop_column("push_outbox", "group_event")
    for column in ("group_kind", "group_message_id", "group_epoch", "group_id"):
        if column == "group_id":
            op.drop_index("ix_pending_messages_group_id", table_name="pending_messages")
        op.drop_column("pending_messages", column)
    for name in ("group_messages", "group_operations", "group_invitations", "group_members", "chat_groups"):
        op.drop_table(name)
