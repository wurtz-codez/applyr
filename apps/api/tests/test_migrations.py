from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.database import get_engine


def test_migration_roundtrip_and_metadata(client):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.check(config)
    command.downgrade(config, "base")
    assert "jobs" not in inspect(get_engine()).get_table_names()
    command.upgrade(config, "head")
    assert "jobs" in inspect(get_engine()).get_table_names()
    command.check(config)
