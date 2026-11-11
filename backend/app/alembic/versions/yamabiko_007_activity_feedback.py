"""Add the table for written feedback on activities

Revision ID: c7a2f4d91e36
Revises: b6f1e8a2d940
Create Date: 2026-11-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7a2f4d91e36"
down_revision: str | None = "b6f1e8a2d940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_feedback",
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            primary_key=True,
            comment="Activity the feedback is about",
        ),
        sa.Column("text", sa.Text(), nullable=False, comment="The feedback, plain text"),
        sa.Column("model", sa.String(length=100), nullable=False, comment="Model that wrote the text"),
        sa.Column("facts_hash", sa.String(length=64), nullable=False, comment="Hash of facts, prompt and model"),
        sa.Column("facts", sa.JSON(), nullable=False, comment="The facts the model was given"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("activity_feedback")
