"""The feedback migration must build the table the ORM model describes, and undo itself."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

import activity_feedback.models as models
from core.database import Base
from tests._helpers.db import _import_all_models

MIGRATION = Path(__file__).resolve().parents[2] / "app" / "alembic" / "versions" / "yamabiko_007_activity_feedback.py"
TABLE = models.ActivityFeedback.__table__


def _load_migration():
    spec = importlib.util.spec_from_file_location("yamabiko_007_activity_feedback", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine():
    _import_all_models()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # The table the new one points to; everything else is not needed.
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["users"], Base.metadata.tables["activities"]])
    yield engine
    engine.dispose()


def _run(engine, step):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        step()


def test_upgrade_creates_what_the_model_describes(engine):
    migration = _load_migration()

    _run(engine, migration.upgrade)

    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE.name)}
    assert set(columns) == {column.name for column in TABLE.columns}
    for column in TABLE.columns:
        assert columns[column.name]["nullable"] == column.nullable, column.name
    assert {index["name"] for index in inspector.get_indexes(TABLE.name)} == {index.name for index in TABLE.indexes}
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys(TABLE.name)} == {
        fk.column.table.name for fk in TABLE.foreign_keys
    }


def test_downgrade_removes_the_table(engine):
    migration = _load_migration()
    _run(engine, migration.upgrade)

    _run(engine, migration.downgrade)

    assert "activity_feedback" not in set(inspect(engine).get_table_names())


def test_the_revision_follows_the_dropped_tables_migration():
    migration = _load_migration()

    assert migration.revision == "c7a2f4d91e36"
    assert migration.down_revision == "b6f1e8a2d940"
