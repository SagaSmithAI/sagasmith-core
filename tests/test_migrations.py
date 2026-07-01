from pathlib import Path

from sqlalchemy import inspect

from sagasmith_core.database import Database, sqlite_database_url


def test_bundled_migration_builds_schema(tmp_path: Path) -> None:
    database = Database(sqlite_database_url(tmp_path / "migrated.db"))
    database.upgrade_schema()
    try:
        assert "campaigns" in inspect(database.engine).get_table_names()
        assert "alembic_version" in inspect(database.engine).get_table_names()
    finally:
        database.dispose()
