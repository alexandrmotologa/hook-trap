import json
import uuid
from typing import Any

from hook_trap.repositories.base import DatabaseManager, utc_now_iso


class WebhookRequestRepository:
    """Repository handling persistence and queries for captured webhook requests."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    async def insert(self, data: dict[str, Any]) -> str:
        """Insert a captured webhook request record."""
        req_id = data.get("id") or str(uuid.uuid4())
        ts = data.get("timestamp") or utc_now_iso()

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

        async with self._db.connection() as conn:
            await conn.execute(
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
            await conn.commit()

        return req_id

    async def list_by_channel(
        self,
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

        async with self._db.connection() as conn:
            count_query = f"SELECT COUNT(*) as cnt FROM webhook_requests{where_clause};"
            async with conn.execute(count_query, params) as cursor:
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
            async with conn.execute(list_query, list_params) as cursor:
                rows = await cursor.fetchall()
                results = [dict(r) for r in rows]

        return results, total

    async def get_by_id(self, channel_id: str, request_id: str) -> dict[str, Any] | None:
        """Retrieve full detail of a specific request."""
        async with self._db.connection() as conn:
            async with conn.execute(
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

    async def delete_by_channel(self, channel_id: str) -> int:
        """Delete all requests and associated logs for a channel."""
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM webhook_requests WHERE channel_id = ?;",
                (channel_id,),
            )
            await conn.commit()
            return cursor.rowcount

    async def increment_replay_count(self, request_id: str) -> None:
        """Increment replay counter for a request."""
        async with self._db.connection() as conn:
            await conn.execute(
                "UPDATE webhook_requests SET replay_count = replay_count + 1 WHERE id = ?;",
                (request_id,),
            )
            await conn.commit()

    async def prune(self, channel_id: str, max_count: int = 500) -> int:
        """Delete oldest requests for a channel if total count exceeds max_count."""
        if max_count <= 0:
            return 0
        async with self._db.connection() as conn:
            cursor = await conn.execute(
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
            await conn.commit()
            return cursor.rowcount

    async def get_all_for_export(self, channel_id: str) -> list[dict[str, Any]]:
        """Retrieve all requests for a channel with parsed details for export."""
        async with self._db.connection() as conn:
            query = """
                SELECT id, channel_id, timestamp, method, path, query_params,
                       headers, body_raw, body_json, content_type, client_ip, replay_count
                FROM webhook_requests
                WHERE channel_id = ?
                ORDER BY timestamp ASC;
            """
            async with conn.execute(query, (channel_id,)) as cursor:
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
