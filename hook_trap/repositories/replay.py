import json
import uuid
from typing import Any

from hook_trap.repositories.base import DatabaseManager, utc_now_iso


class ReplayLogRepository:
    """Repository handling persistence and queries for replay execution logs."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    async def insert(self, data: dict[str, Any]) -> str:
        """Log an HTTP replay execution."""
        log_id = data.get("id") or str(uuid.uuid4())
        ts = data.get("created_at") or utc_now_iso()

        headers_str = (
            json.dumps(data.get("response_headers", {}))
            if isinstance(data.get("response_headers"), dict)
            else str(data.get("response_headers", "{}"))
        )

        async with self._db.connection() as conn:
            await conn.execute(
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
            await conn.commit()

        return log_id

    async def list_by_request_id(self, request_id: str) -> list[dict[str, Any]]:
        """Get replay attempts for a specific webhook request."""
        async with self._db.connection() as conn:
            query = """
                SELECT id, request_id, target_url, status_code, response_headers,
                       response_body, latency_ms, created_at, error
                FROM replay_logs
                WHERE request_id = ?
                ORDER BY created_at DESC;
            """
            async with conn.execute(query, (request_id,)) as cursor:
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
