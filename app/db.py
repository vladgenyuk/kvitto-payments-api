from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.const import ROOT
from app.crud import TariffCrud


class MigrationManager:
    def configuration(self) -> Config:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        return config

    def upgrade(self, connection: Connection) -> None:
        config = self.configuration()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if (
            parsed.drivername not in {"sqlite", "sqlite+aiosqlite"}
            or not parsed.database
            or parsed.database == ":memory:"
        ):
            raise ValueError("Use a file-backed SQLite URL, e.g. sqlite+aiosqlite:///./kvitto.db")
        self.engine = create_async_engine(
            parsed.set(drivername="sqlite+aiosqlite"), connect_args={"timeout": 30}
        )
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)
        self._migrations = MigrationManager()
        event.listen(self.engine.sync_engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(connection: Any, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(self._migrations.upgrade)
        async with self.session() as session:
            await TariffCrud().seed(session)
            await session.commit()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_maker() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
