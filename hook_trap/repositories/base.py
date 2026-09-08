from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class DatabaseManager:
    """Manages SQLite database connections and schema initialization."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        """Database file path."""
        return self._db_path

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provide a managed SQLite connection configured with foreign keys and WAL mode."""
        db_file = Path(self._db_path)
        if db_file.parent and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON;")
            yield conn

    async def initialize(self) -> None:
        """Create database tables, indexes, and run required migrations."""
        async with self.connection() as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")

            # Webhook requests table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_requests (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    query_params TEXT DEFAULT '{}',
                    headers TEXT DEFAULT '{}',
                    body_raw TEXT DEFAULT '',
                    body_json TEXT,
                    content_type TEXT,
                    client_ip TEXT,
                    replay_count INTEGER DEFAULT 0
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_channel ON webhook_requests(channel_id);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_timestamp "
                "ON webhook_requests(timestamp DESC);"
            )

            # Replay logs table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS replay_logs (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    status_code INTEGER,
                    response_headers TEXT DEFAULT '{}',
                    response_body TEXT DEFAULT '',
                    latency_ms REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    error TEXT,
                    FOREIGN KEY (request_id) REFERENCES webhook_requests(id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_replay_request_id ON replay_logs(request_id);"
            )

            # Channels configuration table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT,
                    auto_forward_url TEXT,
                    max_requests INTEGER DEFAULT 500,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # Schema migration check for max_requests column
            async with db.execute("PRAGMA table_info(channels);") as cursor:
                columns = [row["name"] for row in await cursor.fetchall()]
                if "max_requests" not in columns:
                    await db.execute(
                        "ALTER TABLE channels ADD COLUMN max_requests INTEGER DEFAULT 500;"
                    )

            await db.commit()
