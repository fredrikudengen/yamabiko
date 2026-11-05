"""Move users on a removed language to English

Only English and Norwegian Bokmål remain, so any other stored
preferred_language would fail validation when the user is read.

Revision ID: e4b9d3a7c152
Revises: d7a2c91f4e38
Create Date: 2026-11-05 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e4b9d3a7c152"
down_revision: str | None = "d7a2c91f4e38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET preferred_language = 'en' WHERE preferred_language NOT IN ('en', 'nb')")


def downgrade() -> None:
    # The original languages are not kept, and English is valid either way.
    pass
