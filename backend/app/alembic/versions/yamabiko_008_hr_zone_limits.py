"""Keep the heart-rate zone limits on the user

They were kept in each browser, so every device had its own zones and the
server could not use them.

Revision ID: d4e8b2a6f153
Revises: c7a2f4d91e36
Create Date: 2026-11-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e8b2a6f153"
down_revision: str | None = "c7a2f4d91e36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "hr_zone_limits",
            sa.JSON(),
            nullable=True,
            comment="Heart-rate zone limits, four increasing bpm values; null for the defaults",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "hr_zone_limits")
