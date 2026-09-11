"""api_key is_master

Gooclaim: a Master API key may act on behalf of ANY organization — the
caller still supplies X-Organization-ID per request, but the strict
"key's own org must match the header" check is skipped for a key marked
is_master. Used by trusted internal services (e.g. gooclaim-datasources-mcp)
that serve many tenants through one credential, instead of provisioning a
separate API key per tenant. Never settable via any API endpoint — only
ever set directly in the database for the small, deliberate set of keys
that need it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'api_key',
        sa.Column(
            'is_master',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column('api_key', 'is_master')
