import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def verify_migrations() -> None:
    url = os.environ["TEST_DATABASE_URL"]
    # Called only with the fresh DB from a unique verification Compose project.
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if inspect(connection).get_table_names():
                raise RuntimeError(
                    "Migration verification requires an empty test database"
                )
        os.environ["DATABASE_URL"] = url
        config = Config(str(ROOT / "backend/alembic.ini"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
        expected = set(ScriptDirectory.from_config(config).get_heads())
        if current != expected:
            raise RuntimeError("Database revision does not match migration head")
        command.check(config)
        print("Empty PostgreSQL upgrade, revision head and metadata drift: passed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    verify_migrations()
