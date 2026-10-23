"""The segments migration must build the tables the ORM models describe, and undo itself."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

import segments.models as models
from core.database import Base
from tests._helpers.db import _import_all_models

MIGRATION = Path(__file__).resolve().parents[2] / "app" / "alembic" / "versions" / "yamabiko_003_segments.py"
TABLES = (models.Segment.__table__, models.SegmentEffort.__table__)


def _load_migration():
    spec = importlib.util.spec_from_file_location("yamabiko_003_segments", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine():
    _import_all_models()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # The tables the new ones point to; everything else is not needed.
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["users"], Base.metadata.tables["activities"]])
    yield engine
    engine.dispose()


def _run(engine, step):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        step()


def test_upgrade_creates_what_the_models_describe(engine):
    migration = _load_migration()

    _run(engine, migration.upgrade)

    inspector = inspect(engine)
    for table in TABLES:
        columns = {column["name"]: column for column in inspector.get_columns(table.name)}
        assert set(columns) == {column.name for column in table.columns}, table.name
        for column in table.columns:
            assert columns[column.name]["nullable"] == column.nullable, f"{table.name}.{column.name}"
        assert {index["name"] for index in inspector.get_indexes(table.name)} == {index.name for index in table.indexes}
        assert {fk["referred_table"] for fk in inspector.get_foreign_keys(table.name)} == {
            fk.column.table.name for fk in table.foreign_keys
        }
    assert {c["name"] for c in inspector.get_check_constraints("segments")} == {
        "ck_segments_start_radius",
        "ck_segments_end_radius",
    }
    assert [u["name"] for u in inspector.get_unique_constraints("segment_efforts")] == [
        "uq_segment_efforts_segment_activity"
    ]


def test_downgrade_removes_the_tables(engine):
    migration = _load_migration()
    _run(engine, migration.upgrade)

    _run(engine, migration.downgrade)

    assert not {"segments", "segment_efforts"} & set(inspect(engine).get_table_names())


def test_the_revision_follows_the_google_health_migration():
    migration = _load_migration()

    assert migration.revision == "c3e8a5f1b6d4"
    assert migration.down_revision == "8b1d4e6a2c97"
