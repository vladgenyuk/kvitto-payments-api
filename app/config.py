import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    webhook_secret: str

    @classmethod
    def from_env(cls, db_url: str | None = None, webhook_secret: str | None = None) -> "Settings":
        return cls(
            database_url=(
                os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./kvitto.db")
                if db_url is None
                else db_url
            ),
            webhook_secret=(
                os.environ.get("WEBHOOK_SECRET", "") if webhook_secret is None else webhook_secret
            ),
        )
