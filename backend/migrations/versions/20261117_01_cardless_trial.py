"""Persist a single account-bound, server-timed 30-day Base period."""
from datetime import timedelta
from alembic import op
import sqlalchemy as sa

revision = '20261117_01'
down_revision = '20261116_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('cardless_trial_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('cardless_trial_ends_at', sa.DateTime(timezone=True), nullable=True))
    db = op.get_bind()
    users = sa.table('users', sa.column('id', sa.String), sa.column('created_at', sa.DateTime(timezone=True)),
                     sa.column('cardless_trial_started_at', sa.DateTime(timezone=True)), sa.column('cardless_trial_ends_at', sa.DateTime(timezone=True)))
    for row in db.execute(sa.select(users.c.id, users.c.created_at)):
        if row.created_at is None:
            raise RuntimeError('Account creation time missing; trial cannot be inferred')
        db.execute(users.update().where(users.c.id == row.id).values(cardless_trial_started_at=row.created_at,
                   cardless_trial_ends_at=row.created_at + timedelta(days=30)))
    with op.batch_alter_table('users') as batch:
        batch.alter_column('cardless_trial_started_at', existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column('cardless_trial_ends_at', existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_column('cardless_trial_ends_at')
        batch.drop_column('cardless_trial_started_at')
