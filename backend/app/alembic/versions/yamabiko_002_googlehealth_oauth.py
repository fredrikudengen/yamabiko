"""Add Google Health OAuth columns to users_integrations

Revision ID: 8b1d4e6a2c97
Revises: 5f3a9c1d7b42
Create Date: 2026-10-19 22:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b1d4e6a2c97"
down_revision: str | None = "5f3a9c1d7b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users_integrations",
        sa.Column(
            "googlehealth_state",
            sa.String(length=64),
            nullable=True,
            comment="Google Health temporary state for link process",
        ),
    )
    op.add_column(
        "users_integrations",
        sa.Column(
            "googlehealth_token",
            sa.String(length=2048),
            nullable=True,
            comment="Google Health access token encrypted at rest with Fernet key",
        ),
    )
    op.add_column(
        "users_integrations",
        sa.Column(
            "googlehealth_refresh_token",
            sa.String(length=2048),
            nullable=True,
            comment="Google Health refresh token encrypted at rest with Fernet key",
        ),
    )
    op.add_column(
        "users_integrations",
        sa.Column(
            "googlehealth_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Google Health access token expiration date",
        ),
    )
    op.create_index(
        op.f("ix_users_integrations_googlehealth_state"),
        "users_integrations",
        ["googlehealth_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_integrations_googlehealth_state"), table_name="users_integrations")
    op.drop_column("users_integrations", "googlehealth_token_expires_at")
    op.drop_column("users_integrations", "googlehealth_refresh_token")
    op.drop_column("users_integrations", "googlehealth_token")
    op.drop_column("users_integrations", "googlehealth_state")
