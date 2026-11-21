"""Opaque attachment reservations and exact-message/device grants."""
from alembic import op
import sqlalchemy as sa

revision = '20261120_01_media'
down_revision = '20261119_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('media_blobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('owner_device_id', sa.String(36), nullable=False),
        sa.Column('ciphertext_bytes', sa.BigInteger(), nullable=False),
        sa.Column('ciphertext_sha256', sa.String(64), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('upload_token', sa.String(36), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_media_blobs_owner_id', 'media_blobs', ['owner_id'])
    op.create_index('ix_media_blobs_expires_at', 'media_blobs', ['expires_at'])
    op.create_table('media_grants',
        sa.Column('blob_id', sa.String(36), sa.ForeignKey('media_blobs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('pending_messages.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('recipient_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_device_id', sa.String(36), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_media_grants_recipient_device_id', 'media_grants', ['recipient_device_id'])
    op.create_index('ix_media_grants_expires_at', 'media_grants', ['expires_at'])
    op.create_table('media_cleanup',
        sa.Column('blob_id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_media_cleanup_created_at', 'media_cleanup', ['created_at'])


def downgrade():
    db = op.get_bind()
    if (db.execute(sa.text('SELECT count(*) FROM media_blobs')).scalar_one() or
            db.execute(sa.text('SELECT count(*) FROM media_cleanup')).scalar_one()):
        raise RuntimeError('Media must be retired and opaque storage reconciled before downgrade; unsafe downgrade')
    op.drop_index('ix_media_cleanup_created_at', table_name='media_cleanup')
    op.drop_table('media_cleanup')
    op.drop_index('ix_media_grants_expires_at', table_name='media_grants')
    op.drop_index('ix_media_grants_recipient_device_id', table_name='media_grants')
    op.drop_table('media_grants')
    op.drop_index('ix_media_blobs_expires_at', table_name='media_blobs')
    op.drop_index('ix_media_blobs_owner_id', table_name='media_blobs')
    op.drop_table('media_blobs')
