"""Vipi-only deletion, independent receipts, authentication floor and trial dates."""
from alembic import op
import sqlalchemy as sa

revision = '20261117_02'
down_revision = '20261117_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('minimum_auth_time', sa.BigInteger(), nullable=False, server_default='0'))
    constraints = sa.inspect(op.get_bind()).get_unique_constraints('account_deletions')
    name = next(x['name'] for x in constraints if x['column_names'] == ['subject_hash'])
    with op.batch_alter_table('account_deletions', naming_convention={'uq': 'uq_%(table_name)s_%(column_0_name)s'}) as batch:
        batch.drop_constraint(name or 'uq_account_deletions_subject_hash', type_='unique')
        batch.create_index('ix_account_deletions_subject_hash', ['subject_hash'])
    op.create_table('vipi_trial_eligibility',
        sa.Column('subject_hash', sa.String(64), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False))
    # No provider dispatch or legacy pending-job completion. No raw subjects are
    # copied into the ledger. Existing trial dates are captured before deletion.


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text('SELECT count(*) FROM vipi_trial_eligibility')).scalar_one() or db.execute(
            sa.text('SELECT count(*) FROM users WHERE minimum_auth_time > 0')).scalar_one() or db.execute(
            sa.text('SELECT count(*) FROM (SELECT subject_hash FROM account_deletions GROUP BY subject_hash HAVING count(*) > 1) AS repeated')).scalar_one():
        raise RuntimeError('Vipi deletion authentication/eligibility/receipt state must be preserved; unsafe downgrade')
    op.drop_table('vipi_trial_eligibility')
    with op.batch_alter_table('account_deletions') as batch:
        batch.drop_index('ix_account_deletions_subject_hash')
        batch.create_unique_constraint('uq_account_deletions_subject_hash', ['subject_hash'])
    op.drop_column('users', 'minimum_auth_time')
