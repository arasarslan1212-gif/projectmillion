"""alert event details (kind, title, link, date, dedupe key)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29 01:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alert_events", schema=None) as b:
        b.add_column(sa.Column("kind", sa.String(length=40), nullable=True))
        b.add_column(sa.Column("title", sa.Text(), nullable=True))
        b.add_column(sa.Column("url", sa.Text(), nullable=True))
        b.add_column(sa.Column("occurred_on", sa.Date(), nullable=True))
        b.add_column(sa.Column("key", sa.String(length=200), nullable=True))
        b.create_index("ix_alert_events_key", ["key"])


def downgrade() -> None:
    with op.batch_alter_table("alert_events", schema=None) as b:
        b.drop_index("ix_alert_events_key")
        for c in ("key", "occurred_on", "url", "title", "kind"):
            b.drop_column(c)
