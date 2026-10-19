"""Add googlehealth_activity_id to activities

Revision ID: 5f3a9c1d7b42
Revises: a4dd90d4f76e
Create Date: 2026-10-19 21:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f3a9c1d7b42"
down_revision: str | None = "a4dd90d4f76e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "googlehealth_activity_id",
            sa.String(length=32),
            nullable=True,
            comment="Google Health exercise data point ID",
        ),
    )
    op.create_index(
        op.f("ix_activities_googlehealth_activity_id"),
        "activities",
        ["googlehealth_activity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_activities_googlehealth_activity_id"), table_name="activities")
    op.drop_column("activities", "googlehealth_activity_id")
