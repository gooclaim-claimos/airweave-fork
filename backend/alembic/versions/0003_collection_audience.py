"""collection audience

Gooclaim: who a collection's documents may answer — 'members' (the tenant's
members' library, the Portal's Data Sources) or 'staff' (searched by Orion,
the staff coworker, only). Every existing collection is a members' library:
that is what the Portal has always uploaded to. Enforced by caller in
gooclaim-datasources-mcp.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'collection',
        sa.Column('audience', sa.String(), nullable=False, server_default='members'),
    )
    op.create_check_constraint(
        'ck_collection_audience', 'collection', "audience IN ('members', 'staff')"
    )


def downgrade():
    op.drop_constraint('ck_collection_audience', 'collection', type_='check')
    op.drop_column('collection', 'audience')
