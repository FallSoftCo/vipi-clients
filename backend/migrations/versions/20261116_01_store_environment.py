"""Namespace verified store entitlements by environment; ambiguous grants fail closed."""
from alembic import op
import sqlalchemy as sa

revision = "20261116_01"
down_revision = "20261107_05"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    bad = db.execute(sa.text("SELECT count(*) FROM entitlements WHERE (environment IS NULL OR environment NOT IN ('Production','Sandbox')) AND (provider_reference IS NOT NULL OR verified_at IS NOT NULL)" )).scalar_one()
    if bad:
        raise RuntimeError("Resolve ambiguous verified store environments before upgrade")
    # Unverified supersession tombstones never grant and do not infer store environment.
    db.execute(sa.text("UPDATE entitlements SET environment='Unknown' WHERE environment IS NULL OR environment NOT IN ('Production','Sandbox')"))
    with op.batch_alter_table('entitlements', naming_convention={'uq': '%(table_name)s_%(column_0_name)s_%(column_1_name)s_key'}) as batch:
        batch.drop_constraint('entitlements_store_transaction_id_key', type_='unique')
        batch.alter_column('environment', existing_type=sa.String(16), nullable=False)
        batch.create_unique_constraint('uq_entitlements_store_environment_transaction', ['store','environment','transaction_id'])


def downgrade():
    db = op.get_bind()
    duplicates = db.execute(sa.text("SELECT count(*) FROM (SELECT store, transaction_id FROM entitlements GROUP BY store, transaction_id HAVING count(*) > 1) AS collisions")).scalar_one()
    if duplicates:
        raise RuntimeError("Resolve cross-environment transaction collisions before downgrade")
    with op.batch_alter_table('entitlements', naming_convention={'uq': '%(table_name)s_%(column_0_name)s_%(column_1_name)s_key'}) as batch:
        batch.drop_constraint('uq_entitlements_store_environment_transaction', type_='unique')
        batch.alter_column('environment', existing_type=sa.String(16), nullable=True)
        batch.create_unique_constraint('entitlements_store_transaction_id_key', ['store','transaction_id'])
