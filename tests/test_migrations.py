import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.db import Database, MigrationManager
from app.models import Base


def test_migration_upgrade_downgrade_and_model_consistency(db_url):
    def check_migrations(connection):
        config = MigrationManager().configuration()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {
            "tariffs",
            "payments",
            "alembic_version",
        }
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        assert "payments" in inspect(connection).get_table_names()

    async def run():
        database = Database(db_url)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(check_migrations)
        finally:
            await database.close()

    asyncio.run(run())
