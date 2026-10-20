"""The Yamabiko migrations must extend Endurain's history, not fork it."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _script() -> ScriptDirectory:
    config = Config(str(APP_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(APP_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_history_has_a_single_head():
    # Two heads make `alembic upgrade head` fail at startup.
    assert len(_script().get_heads()) == 1


def test_yamabiko_migrations_come_last_in_order():
    script = _script()
    (head,) = script.get_heads()
    chain = [revision.revision for revision in script.walk_revisions()]  # newest first
    assert chain[0] == head == "8b1d4e6a2c97"
    assert chain[1] == "5f3a9c1d7b42"
