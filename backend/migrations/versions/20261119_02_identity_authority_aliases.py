"""Retain identity migration aliases independently of discontinued trials."""
from alembic import op
import sqlalchemy as sa

revision = '20261119_02'
down_revision = '20261119_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('identity_authority_aliases',
        sa.Column('source_hash', sa.String(64), primary_key=True),
        sa.Column('target_hash', sa.String(64), nullable=False))
    op.create_index('ix_identity_authority_aliases_target_hash', 'identity_authority_aliases', ['target_hash'])
    # Existing historical trial links use the same lifecycle HMAC family. No
    # provider call, raw identity, account ID or token is needed for preservation.
    db = op.get_bind()
    conflicts = db.execute(sa.text('SELECT source_hash FROM vipi_trial_eligibility_links GROUP BY source_hash HAVING COUNT(DISTINCT target_hash) > 1')).first()
    if conflicts:
        raise RuntimeError('Ambiguous historical identity aliases require reconciliation')
    db.execute(sa.text('INSERT INTO identity_authority_aliases (source_hash,target_hash) SELECT DISTINCT source_hash,target_hash FROM vipi_trial_eligibility_links'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM identity_authority_aliases')).scalar_one():
        raise RuntimeError('Identity aliases must be preserved; unsafe downgrade')
    op.drop_index('ix_identity_authority_aliases_target_hash', table_name='identity_authority_aliases')
    op.drop_table('identity_authority_aliases')
