"""Namespaced shared login, exact migration receipts and original trial links."""
from alembic import op
import sqlalchemy as sa

revision = '20261117_03'
down_revision = '20261117_02'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.alter_column('subject', existing_type=sa.String(128), type_=sa.String(256), existing_nullable=False)
    with op.batch_alter_table('rate_windows') as batch:
        batch.alter_column('subject', existing_type=sa.String(128), type_=sa.String(256), existing_nullable=False)
    op.create_table('identity_link_receipts',
        sa.Column('request_id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), nullable=False, unique=True),
        sa.Column('source_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('target_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('device_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('vipi_trial_eligibility_links',
        sa.Column('source_hash', sa.String(64), primary_key=True),
        sa.Column('target_hash', sa.String(64), primary_key=True))


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text('SELECT count(*) FROM identity_link_receipts')).scalar_one() or db.execute(
            sa.text('SELECT count(*) FROM vipi_trial_eligibility_links')).scalar_one() or db.execute(
            sa.text("SELECT count(*) FROM users WHERE subject LIKE 'fallsoft-vipi-production:%'")).scalar_one():
        raise RuntimeError('Shared identity bindings/eligibility must be preserved; unsafe downgrade')
    op.drop_table('vipi_trial_eligibility_links')
    op.drop_table('identity_link_receipts')
    with op.batch_alter_table('rate_windows') as batch:
        batch.alter_column('subject', existing_type=sa.String(256), type_=sa.String(128), existing_nullable=False)
    with op.batch_alter_table('users') as batch:
        batch.alter_column('subject', existing_type=sa.String(256), type_=sa.String(128), existing_nullable=False)
