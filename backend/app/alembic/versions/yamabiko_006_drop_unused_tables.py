"""Drop the tables of features Yamabiko has removed

Gear, health, goals, followers, notifications, sign-up tokens and single
sign-on are gone from the code, so their tables and the two columns that
pointed into them go too. Laps, sets, workout steps and exercise titles
stay: file import still writes them.

This cannot be undone. Take a database backup before upgrading.

Revision ID: b6f1e8a2d940
Revises: e4b9d3a7c152
Create Date: 2026-11-06 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b6f1e8a2d940"
down_revision: str | None = "e4b9d3a7c152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROPPED_TABLES: tuple[str, ...] = (
    "followers",
    "gear_components",
    "users_default_gear",
    "gear",
    "users_goals",
    "health_fasting",
    "health_poop",
    "health_sleep",
    "health_steps",
    "health_targets",
    "health_water",
    "health_weight",
    "notifications",
    "users_identity_providers",
    "idp_link_tokens",
    "oauth_states",
    "identity_providers",
    "sign_up_tokens",
)


def upgrade() -> None:
    # Columns in kept tables that reference dropped tables. Dropping a
    # column also drops its foreign key and index.
    op.execute("ALTER TABLE activities DROP COLUMN IF EXISTS gear_id")
    op.execute("ALTER TABLE users_sessions DROP COLUMN IF EXISTS oauth_state_id")
    op.execute("ALTER TABLE users_sessions DROP COLUMN IF EXISTS tokens_exchanged")

    # One statement, so foreign keys between the dropped tables need no
    # particular order and no CASCADE.
    op.execute("DROP TABLE IF EXISTS " + ", ".join(DROPPED_TABLES))


def downgrade() -> None:
    raise NotImplementedError("Dropped tables cannot be restored. Restore the database from a backup instead.")
