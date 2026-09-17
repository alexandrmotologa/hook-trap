import json
import uuid
from typing import Any

from hook_trap.repositories.base import DatabaseManager, utc_now_iso


class ScenarioRepository:
    """Repository handling persistence and queries for webhook scenarios and steps."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    async def create(
        self,
        scenario_data: dict[str, Any],
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new scenario and optionally persist its ordered steps."""
        scenario_id = scenario_data.get("id") or str(uuid.uuid4())
        channel_id = scenario_data["channel_id"]
        name = scenario_data["name"]
        description = scenario_data.get("description")
        target_url = scenario_data["target_url"]
        delay_ms = scenario_data.get("delay_between_steps_ms", 500)
        created_at = scenario_data.get("created_at") or utc_now_iso()

        async with self._db.connection() as conn:
            # Ensure the channel exists so foreign key constraint succeeds
            await conn.execute(
                """
                INSERT OR IGNORE INTO channels (channel_id, created_at, updated_at)
                VALUES (?, ?, ?);
                """,
                (channel_id, created_at, created_at),
            )

            await conn.execute(
                """
                INSERT INTO scenarios (
                    id, channel_id, name, description,
                    target_url, delay_between_steps_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (scenario_id, channel_id, name, description, target_url, delay_ms, created_at),
            )

            created_steps: list[dict[str, Any]] = []
            if steps:
                for idx, s in enumerate(steps):
                    step_id = s.get("id") or str(uuid.uuid4())
                    step_order = s.get("step_order", idx + 1)
                    step_name = s.get("name", f"Step {idx + 1}")
                    method = s.get("method", "POST").upper()
                    path_suffix = s.get("path_suffix", "")
                    headers = s.get("headers", {})
                    if isinstance(headers, dict):
                        headers_json = json.dumps(headers)
                    else:
                        headers_json = str(headers)
                    payload_raw = s.get("payload_raw", "")
                    expected_status = s.get("expected_status", 200)

                    await conn.execute(
                        """
                        INSERT INTO scenario_steps (
                            id, scenario_id, step_order, name, method, path_suffix,
                            headers_json, payload_raw, expected_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            step_id,
                            scenario_id,
                            step_order,
                            step_name,
                            method,
                            path_suffix,
                            headers_json,
                            payload_raw,
                            expected_status,
                        ),
                    )
                    created_steps.append(
                        {
                            "id": step_id,
                            "scenario_id": scenario_id,
                            "step_order": step_order,
                            "name": step_name,
                            "method": method,
                            "path_suffix": path_suffix,
                            "headers": headers if isinstance(headers, dict) else {},
                            "payload_raw": payload_raw,
                            "expected_status": expected_status,
                        }
                    )

            await conn.commit()

        return {
            "id": scenario_id,
            "channel_id": channel_id,
            "name": name,
            "description": description,
            "target_url": target_url,
            "delay_between_steps_ms": delay_ms,
            "created_at": created_at,
            "steps": created_steps,
        }

    async def get(self, scenario_id: str) -> dict[str, Any] | None:
        """Retrieve a scenario with all ordered steps."""
        async with self._db.connection() as conn:
            query = """
                SELECT id, channel_id, name, description,
                       target_url, delay_between_steps_ms, created_at
                FROM scenarios
                WHERE id = ?;
            """
            async with conn.execute(query, (scenario_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                scenario = dict(row)

            steps_query = """
                SELECT id, scenario_id, step_order, name, method, path_suffix,
                       headers_json, payload_raw, expected_status
                FROM scenario_steps
                WHERE scenario_id = ?
                ORDER BY step_order ASC;
            """
            async with conn.execute(steps_query, (scenario_id,)) as cursor:
                step_rows = await cursor.fetchall()
                steps = []
                for s_row in step_rows:
                    step_dict = dict(s_row)
                    try:
                        step_dict["headers"] = json.loads(step_dict.pop("headers_json", "{}"))
                    except Exception:
                        step_dict["headers"] = {}
                    steps.append(step_dict)

            scenario["steps"] = steps
            return scenario

    async def list_by_channel(self, channel_id: str) -> list[dict[str, Any]]:
        """List all scenarios for a specific channel with their steps."""
        async with self._db.connection() as conn:
            query = """
                SELECT id, channel_id, name, description,
                       target_url, delay_between_steps_ms, created_at
                FROM scenarios
                WHERE channel_id = ?
                ORDER BY created_at DESC;
            """
            async with conn.execute(query, (channel_id,)) as cursor:
                scenario_rows = await cursor.fetchall()
                scenarios = [dict(r) for r in scenario_rows]

            for sc in scenarios:
                steps_query = """
                    SELECT id, scenario_id, step_order, name, method, path_suffix,
                           headers_json, payload_raw, expected_status
                    FROM scenario_steps
                    WHERE scenario_id = ?
                    ORDER BY step_order ASC;
                """
                async with conn.execute(steps_query, (sc["id"],)) as cursor:
                    step_rows = await cursor.fetchall()
                    steps = []
                    for s_row in step_rows:
                        step_dict = dict(s_row)
                        try:
                            step_dict["headers"] = json.loads(step_dict.pop("headers_json", "{}"))
                        except Exception:
                            step_dict["headers"] = {}
                        steps.append(step_dict)
                sc["steps"] = steps

            return scenarios

    async def update(
        self,
        scenario_id: str,
        data: dict[str, Any],
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Update scenario fields and optionally replace its steps."""
        existing = await self.get(scenario_id)
        if not existing:
            return None

        new_name = data.get("name") if data.get("name") is not None else existing["name"]
        new_desc = (
            data.get("description")
            if data.get("description") is not None
            else existing["description"]
        )
        new_target = (
            data.get("target_url")
            if data.get("target_url") is not None
            else existing["target_url"]
        )
        new_delay = (
            data.get("delay_between_steps_ms")
            if data.get("delay_between_steps_ms") is not None
            else existing["delay_between_steps_ms"]
        )

        async with self._db.connection() as conn:
            await conn.execute(
                """
                UPDATE scenarios
                SET name = ?, description = ?, target_url = ?, delay_between_steps_ms = ?
                WHERE id = ?;
                """,
                (new_name, new_desc, new_target, new_delay, scenario_id),
            )

            if steps is not None:
                await conn.execute(
                    "DELETE FROM scenario_steps WHERE scenario_id = ?;", (scenario_id,)
                )
                for idx, s in enumerate(steps):
                    step_id = s.get("id") or str(uuid.uuid4())
                    step_order = s.get("step_order", idx + 1)
                    step_name = s.get("name", f"Step {idx + 1}")
                    method = s.get("method", "POST").upper()
                    path_suffix = s.get("path_suffix", "")
                    headers = s.get("headers", {})
                    if isinstance(headers, dict):
                        headers_json = json.dumps(headers)
                    else:
                        headers_json = str(headers)
                    payload_raw = s.get("payload_raw", "")
                    expected_status = s.get("expected_status", 200)

                    await conn.execute(
                        """
                        INSERT INTO scenario_steps (
                            id, scenario_id, step_order, name, method, path_suffix,
                            headers_json, payload_raw, expected_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            step_id,
                            scenario_id,
                            step_order,
                            step_name,
                            method,
                            path_suffix,
                            headers_json,
                            payload_raw,
                            expected_status,
                        ),
                    )

            await conn.commit()

        return await self.get(scenario_id)

    async def delete(self, scenario_id: str) -> bool:
        """Delete a scenario and its cascade-related steps."""
        async with self._db.connection() as conn:
            cursor = await conn.execute("DELETE FROM scenarios WHERE id = ?;", (scenario_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def add_step(self, scenario_id: str, step_data: dict[str, Any]) -> dict[str, Any]:
        """Add a single step to an existing scenario."""
        step_id = step_data.get("id") or str(uuid.uuid4())
        step_name = step_data.get("name", "New Step")
        method = step_data.get("method", "POST").upper()
        path_suffix = step_data.get("path_suffix", "")
        headers = step_data.get("headers", {})
        if isinstance(headers, dict):
            headers_json = json.dumps(headers)
        else:
            headers_json = str(headers)
        payload_raw = step_data.get("payload_raw", "")
        expected_status = step_data.get("expected_status", 200)

        async with self._db.connection() as conn:
            if "step_order" in step_data and step_data["step_order"] is not None:
                step_order = int(step_data["step_order"])
            else:
                query = (
                    "SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order "
                    "FROM scenario_steps WHERE scenario_id = ?;"
                )
                async with conn.execute(query, (scenario_id,)) as cur:
                    row = await cur.fetchone()
                    step_order = row["next_order"] if row else 1

            await conn.execute(
                """
                INSERT INTO scenario_steps (
                    id, scenario_id, step_order, name, method, path_suffix,
                    headers_json, payload_raw, expected_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    step_id,
                    scenario_id,
                    step_order,
                    step_name,
                    method,
                    path_suffix,
                    headers_json,
                    payload_raw,
                    expected_status,
                ),
            )
            await conn.commit()

        return {
            "id": step_id,
            "scenario_id": scenario_id,
            "step_order": step_order,
            "name": step_name,
            "method": method,
            "path_suffix": path_suffix,
            "headers": headers if isinstance(headers, dict) else {},
            "payload_raw": payload_raw,
            "expected_status": expected_status,
        }

    async def delete_step(self, scenario_id: str, step_id: str) -> bool:
        """Delete a single step from a scenario."""
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM scenario_steps WHERE scenario_id = ? AND id = ?;",
                (scenario_id, step_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
