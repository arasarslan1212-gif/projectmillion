"""calibration changes (track record recalibration log)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28 23:50:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fitted_on", sa.Date(), nullable=False),
        sa.Column("data_cutoff", sa.Date(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("sigma_scale", sa.Float(), nullable=False),
        sa.Column("prob_map_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column("config_hash", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calibration_changes_fitted_on", "calibration_changes", ["fitted_on"])


def downgrade() -> None:
    op.drop_index("ix_calibration_changes_fitted_on", table_name="calibration_changes")
    op.drop_table("calibration_changes")
