"""The zone limits migration adds the column the user model describes."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

MIGRATION = Path(__file__).resolve().parents[2] / "app" / "alembic" / "versions" / "yamabiko_008_hr_zone_limits.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("yamabiko_008_hr_zone_limits", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_a_nullable_column_for_the_limits():
    engine = create_engine("sqlite://")
    sa.Table("users", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True)).create(engine)

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        _load_migration().upgrade()

    columns = {column["name"]: column for column in inspect(engine).get_columns("users")}
    assert columns["hr_zone_limits"]["nullable"] is True
    engine.dispose()


def test_the_revision_follows_the_feedback_migration():
    migration = _load_migration()

    assert migration.revision == "d4e8b2a6f153"
    assert migration.down_revision == "c7a2f4d91e36"
