"""analyst action headline

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28 04:10:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analyst_actions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("headline", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analyst_actions", schema=None) as batch_op:
        batch_op.drop_column("headline")
