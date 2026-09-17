import asyncio
import logging
import time

import httpx

from hook_trap.database import get_scenario
from hook_trap.models import ScenarioRunResult, ScenarioStepResult
from hook_trap.ws_manager import ConnectionManager, ws_manager

logger = logging.getLogger("hook_trap.scenario_runner")

FILTERED_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
}


class ScenarioRunner:
    """Service that executes multi-step webhook scenario sequences with delay and assertions."""

    def __init__(
        self,
        connection_manager: ConnectionManager | None = None,
        filtered_headers: set[str] | None = None,
    ) -> None:
        self._ws_manager = connection_manager or ws_manager
        self._filtered_headers = filtered_headers or FILTERED_HEADERS

    def filter_headers(self, incoming_headers: dict[str, str]) -> dict[str, str]:
        """Filter out transport and hop-by-hop headers."""
        return {
            k: v for k, v in incoming_headers.items() if k.lower() not in self._filtered_headers
        }

    async def run(
        self,
        db_path: str,
        scenario_id: str,
        target_url_override: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> ScenarioRunResult:
        """
        Execute an ordered scenario sequence against the target URL.
        Streams real-time step progress over WebSockets and asserts response statuses.
        """
        scenario = await get_scenario(db_path, scenario_id)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")

        target_url = target_url_override or scenario["target_url"]
        channel_id = scenario["channel_id"]
        steps = scenario.get("steps", [])
        delay_ms = scenario.get("delay_between_steps_ms", 500)

        run_start = time.perf_counter()

        await self._ws_manager.broadcast(
            channel_id,
            {
                "event": "scenario_run_started",
                "data": {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario["name"],
                    "target_url": target_url,
                    "total_steps": len(steps),
                },
            },
        )

        step_results: list[ScenarioStepResult] = []

        for idx, step in enumerate(steps):
            path_suffix = step.get("path_suffix", "").strip()
            base = target_url.rstrip("/")
            if path_suffix:
                url = f"{base}/{path_suffix.lstrip('/')}"
            else:
                url = base

            method = step.get("method", "POST").upper()
            headers_to_send = self.filter_headers(step.get("headers", {}))
            body_raw = step.get("payload_raw", "")
            expected_status = step.get("expected_status", 200)

            content = (
                body_raw.encode("utf-8")
                if method not in ("GET", "HEAD") and isinstance(body_raw, str)
                else None
            )

            status_code: int | None = None
            response_body = ""
            error_msg: str | None = None

            step_start = time.perf_counter()
            try:
                if client is not None:
                    resp = await client.request(
                        method=method,
                        url=url,
                        content=content,
                        headers=headers_to_send,
                    )
                    status_code = resp.status_code
                    response_body = resp.text[:4096]
                else:
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http_c:
                        resp = await http_c.request(
                            method=method,
                            url=url,
                            content=content,
                            headers=headers_to_send,
                        )
                        status_code = resp.status_code
                        response_body = resp.text[:4096]
            except httpx.TimeoutException:
                error_msg = f"Step timed out after 15s when calling {url}"
            except httpx.ConnectError:
                error_msg = f"Failed to connect to {url}. Ensure server is running."
            except Exception as exc:
                error_msg = f"Delivery error: {exc}"

            elapsed_ms = round((time.perf_counter() - step_start) * 1000, 2)
            passed = status_code == expected_status

            step_result = ScenarioStepResult(
                step_id=step["id"],
                step_name=step["name"],
                step_order=step["step_order"],
                method=method,
                url=url,
                expected_status=expected_status,
                actual_status=status_code,
                latency_ms=elapsed_ms,
                passed=passed,
                response_body=response_body,
                error=error_msg,
            )
            step_results.append(step_result)

            await self._ws_manager.broadcast(
                channel_id,
                {
                    "event": "scenario_step_completed",
                    "data": step_result.model_dump(),
                },
            )

            if idx < len(steps) - 1 and delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

        total_duration_ms = round((time.perf_counter() - run_start) * 1000, 2)
        passed_steps = sum(1 for r in step_results if r.passed)
        failed_steps = len(step_results) - passed_steps
        success = failed_steps == 0

        final_result = ScenarioRunResult(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            target_url=target_url,
            total_steps=len(steps),
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            success=success,
            total_duration_ms=total_duration_ms,
            step_results=step_results,
        )

        await self._ws_manager.broadcast(
            channel_id,
            {
                "event": "scenario_run_completed",
                "data": final_result.model_dump(),
            },
        )

        return final_result


# Singleton instance
scenario_runner = ScenarioRunner()
