"""Add the cells an activity's track passed through

Revision ID: d7a2c91f4e38
Revises: c3e8a5f1b6d4
Create Date: 2026-10-29 23:40:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7a2c91f4e38"
down_revision: str | None = "c3e8a5f1b6d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_cells",
        sa.Column("activity_id", sa.Integer(), nullable=False, comment="Activity that passed through the cell"),
        sa.Column("cell_x", sa.Integer(), nullable=False, comment="Web Mercator cell x at grid_zoom"),
        sa.Column("cell_y", sa.Integer(), nullable=False, comment="Web Mercator cell y at grid_zoom"),
        sa.Column("grid_zoom", sa.SmallInteger(), nullable=False, comment="Zoom the cell indices are given at"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("activity_id", "cell_x", "cell_y"),
    )
    op.create_index("ix_activity_cells_cell", "activity_cells", ["cell_x", "cell_y"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activity_cells_cell", table_name="activity_cells")
    op.drop_table("activity_cells")
