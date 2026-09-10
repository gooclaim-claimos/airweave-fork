"""collection is_public

Gooclaim: a Public collection is readable by every organization (used for
shared/regulatory knowledge curated via Console), not just its owning org.
Write access to this flag is gated at the API layer (platform admin only),
not by the database.

Revision ID: 0001
Revises: 0000
Create Date: 2026-09-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = '0000'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'collection',
        sa.Column(
            'is_public',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column('collection', 'is_public')
