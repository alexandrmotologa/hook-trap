import json
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def init_db(db_path: str) -> None:
    """Initialize SQLite database tables and indexes."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

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
            "CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON webhook_requests(timestamp DESC);"
        )

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
        async with db.execute("PRAGMA table_info(channels);") as cursor:
            cols = [r[1] for r in await cursor.fetchall()]
            if "max_requests" not in cols:
                await db.execute(
                    "ALTER TABLE channels ADD COLUMN max_requests INTEGER DEFAULT 500;"
                )
        await db.commit()


async def insert_webhook_request(db_path: str, data: dict[str, Any]) -> str:
    """Insert a captured webhook request record."""
    req_id = data.get("id") or str(uuid.uuid4())
    ts = data.get("timestamp") or _utc_now_iso()
    query_params_str = (
        json.dumps(data.get("query_params", {}))
        if isinstance(data.get("query_params"), dict)
        else str(data.get("query_params", "{}"))
    )
    headers_str = (
        json.dumps(data.get("headers", {}))
        if isinstance(data.get("headers"), dict)
        else str(data.get("headers", "{}"))
    )
    body_json_str = None
    if data.get("body_json") is not None:
        body_json_str = (
            json.dumps(data["body_json"])
            if not isinstance(data["body_json"], str)
            else data["body_json"]
        )

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(
            """
            INSERT INTO webhook_requests (
                id, channel_id, timestamp, method, path, query_params,
                headers, body_raw, body_json, content_type, client_ip, replay_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                req_id,
                data["channel_id"],
                ts,
                data["method"],
                data["path"],
                query_params_str,
                headers_str,
                data.get("body_raw", ""),
                body_json_str,
                data.get("content_type"),
                data.get("client_ip"),
                data.get("replay_count", 0),
            ),
        )
        await db.commit()
    return req_id


async def get_webhook_requests(
    db_path: str,
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
    method: str | None = None,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve paginated summaries and total count for a channel."""
    conditions = ["channel_id = ?"]
    params: list[Any] = [channel_id]

    if method and method.upper() != "ALL":
        conditions.append("method = ?")
        params.append(method.upper())

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(path LIKE ? OR body_raw LIKE ? OR headers LIKE ?)")
        params.extend([term, term, term])

    where_clause = " WHERE " + " AND ".join(conditions)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        count_query = f"SELECT COUNT(*) as cnt FROM webhook_requests{where_clause};"
        async with db.execute(count_query, params) as cursor:
            row = await cursor.fetchone()
            total = row["cnt"] if row else 0

        list_query = f"""
            SELECT id, channel_id, timestamp, method, path, content_type,
                   client_ip, replay_count, length(body_raw) as body_size,
                   substr(body_raw, 1, 160) as body_preview
            FROM webhook_requests
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?;
        """
        list_params = params + [limit, offset]
        async with db.execute(list_query, list_params) as cursor:
            rows = await cursor.fetchall()
            results = [dict(r) for r in rows]

    return results, total


async def get_webhook_request_detail(
    db_path: str, channel_id: str, request_id: str
) -> dict[str, Any] | None:
    """Retrieve full detail of a specific request."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, channel_id, timestamp, method, path, query_params,
                   headers, body_raw, body_json, content_type, client_ip, replay_count
            FROM webhook_requests
            WHERE channel_id = ? AND id = ?;
            """,
            (channel_id, request_id),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["query_params"] = json.loads(data["query_params"] or "{}")
            except Exception:
                data["query_params"] = {}
            try:
                data["headers"] = json.loads(data["headers"] or "{}")
            except Exception:
                data["headers"] = {}
            if data["body_json"]:
                try:
                    data["body_json"] = json.loads(data["body_json"])
                except Exception:
                    pass
            return data


async def delete_channel_requests(db_path: str, channel_id: str) -> int:
    """Delete all requests and associated logs for a channel."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        cursor = await db.execute(
            "DELETE FROM webhook_requests WHERE channel_id = ?;",
            (channel_id,),
        )
        await db.commit()
        return cursor.rowcount


async def increment_replay_count(db_path: str, request_id: str) -> None:
    """Increment replay counter for a request."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE webhook_requests SET replay_count = replay_count + 1 WHERE id = ?;",
            (request_id,),
        )
        await db.commit()


async def insert_replay_log(db_path: str, data: dict[str, Any]) -> str:
    """Log an HTTP replay execution."""
    log_id = data.get("id") or str(uuid.uuid4())
    ts = data.get("created_at") or _utc_now_iso()
    headers_str = (
        json.dumps(data.get("response_headers", {}))
        if isinstance(data.get("response_headers"), dict)
        else str(data.get("response_headers", "{}"))
    )

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(
            """
            INSERT INTO replay_logs (
                id, request_id, target_url, status_code, response_headers,
                response_body, latency_ms, created_at, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                log_id,
                data["request_id"],
                data["target_url"],
                data.get("status_code"),
                headers_str,
                data.get("response_body", ""),
                data.get("latency_ms", 0.0),
                ts,
                data.get("error"),
            ),
        )
        await db.commit()
    return log_id


async def get_replay_logs_for_request(db_path: str, request_id: str) -> list[dict[str, Any]]:
    """Get replay attempts for a specific webhook request."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, request_id, target_url, status_code, response_headers,
                   response_body, latency_ms, created_at, error
            FROM replay_logs
            WHERE request_id = ?
            ORDER BY created_at DESC;
            """,
            (request_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["response_headers"] = json.loads(item["response_headers"] or "{}")
                except Exception:
                    item["response_headers"] = {}
                results.append(item)
            return results


async def prune_channel_requests(
    db_path: str, channel_id: str, max_count: int = 500
) -> int:
    """Delete oldest requests for a channel if total count exceeds max_count."""
    if max_count <= 0:
        return 0
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        cursor = await db.execute(
            """
            DELETE FROM webhook_requests
            WHERE channel_id = ? AND id NOT IN (
                SELECT id FROM webhook_requests
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            );
            """,
            (channel_id, channel_id, max_count),
        )
        await db.commit()
        return cursor.rowcount


async def get_channel_config(db_path: str, channel_id: str) -> dict[str, Any] | None:
    """Retrieve persisted channel configuration."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = (
            "SELECT channel_id, name, auto_forward_url, max_requests, created_at, updated_at "
            "FROM channels WHERE channel_id = ?;"
        )
        async with db.execute(query, (channel_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("max_requests") is None:
                data["max_requests"] = 500
            return data


async def upsert_channel_config(
    db_path: str,
    channel_id: str,
    name: str | None = None,
    auto_forward_url: str | None = None,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Create or update channel configuration."""
    now = _utc_now_iso()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        sel_query = (
            "SELECT channel_id, name, auto_forward_url, max_requests, created_at "
            "FROM channels WHERE channel_id = ?;"
        )
        async with db.execute(sel_query, (channel_id,)) as cursor:
            existing = await cursor.fetchone()

        if existing:
            new_name = name if name is not None else existing["name"]
            new_auto_forward = (
                auto_forward_url if auto_forward_url is not None else existing["auto_forward_url"]
            )
            new_max_req = (
                max_requests
                if max_requests is not None
                else (existing["max_requests"] or 500)
            )
            await db.execute(
                """
                UPDATE channels
                SET name = ?, auto_forward_url = ?, max_requests = ?, updated_at = ?
                WHERE channel_id = ?;
                """,
                (new_name, new_auto_forward, new_max_req, now, channel_id),
            )
            created_at = existing["created_at"]
        else:
            new_name = name
            new_auto_forward = auto_forward_url
            new_max_req = max_requests if max_requests is not None else 500
            created_at = now
            await db.execute(
                """
                INSERT INTO channels (
                    channel_id, name, auto_forward_url, max_requests, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (channel_id, new_name, new_auto_forward, new_max_req, created_at, now),
            )
        await db.commit()

    return {
        "channel_id": channel_id,
        "name": new_name,
        "auto_forward_url": new_auto_forward,
        "max_requests": new_max_req,
        "created_at": created_at,
        "updated_at": now,
    }


async def get_all_channel_requests_for_export(
    db_path: str, channel_id: str
) -> list[dict[str, Any]]:
    """Retrieve all requests for a channel with parsed details for export."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT id, channel_id, timestamp, method, path, query_params,
                   headers, body_raw, body_json, content_type, client_ip, replay_count
            FROM webhook_requests
            WHERE channel_id = ?
            ORDER BY timestamp ASC;
        """
        async with db.execute(query, (channel_id,)) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["query_params"] = json.loads(item["query_params"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    item["query_params"] = {}
                try:
                    item["headers"] = json.loads(item["headers"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    item["headers"] = {}
                if item["body_json"]:
                    try:
                        item["body_json"] = json.loads(item["body_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append(item)
            return results
