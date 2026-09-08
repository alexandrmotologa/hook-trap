import logging
import time
from typing import Any

import httpx

from hook_trap.database import (
    get_webhook_request_detail,
    increment_replay_count,
    insert_replay_log,
)
from hook_trap.ws_manager import ConnectionManager, ws_manager

logger = logging.getLogger("hook_trap.forwarder")

FILTERED_FORWARD_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
}


class WebhookForwarder:
    """Service responsible for HTTP forwarding and replay of captured webhooks."""

    def __init__(
        self,
        connection_manager: ConnectionManager | None = None,
        filtered_headers: set[str] | None = None,
    ) -> None:
        self._ws_manager = connection_manager or ws_manager
        self._filtered_headers = filtered_headers or FILTERED_FORWARD_HEADERS

    def filter_headers(self, incoming_headers: dict[str, str]) -> dict[str, str]:
        """Strip hop-by-hop and host headers before forwarding."""
        return {
            k: v for k, v in incoming_headers.items() if k.lower() not in self._filtered_headers
        }

    async def forward(
        self,
        db_path: str,
        channel_id: str,
        request_id: str,
        target_url: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """
        Execute an HTTP forward/replay of a captured request to target_url.
        Records performance, response details, and errors to SQLite.
        """
        req_detail = await get_webhook_request_detail(db_path, channel_id, request_id)
        if not req_detail:
            raise ValueError(f"Request {request_id} not found in channel {channel_id}")

        headers_to_send = self.filter_headers(req_detail.get("headers", {}))
        method = req_detail.get("method", "POST").upper()
        body_raw = req_detail.get("body_raw", "")
        query_params = req_detail.get("query_params", {})

        body_bytes = body_raw.encode("utf-8") if isinstance(body_raw, str) else body_raw

        status_code: int | None = None
        response_headers: dict[str, str] = {}
        response_body = ""
        error_msg: str | None = None

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.request(
                    method=method,
                    url=target_url,
                    params=query_params,
                    content=body_bytes if method not in ("GET", "HEAD") else None,
                    headers=headers_to_send,
                )
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                status_code = resp.status_code
                response_headers = dict(resp.headers)
                response_body = resp.text[:65536]
        except httpx.TimeoutException:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            error_msg = f"Request to {target_url} timed out after {timeout}s"
        except httpx.ConnectError:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            error_msg = f"Failed to connect to {target_url}. Is the service running?"
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            error_msg = f"Forwarding error: {exc}"

        log_entry = {
            "request_id": request_id,
            "target_url": target_url,
            "status_code": status_code,
            "response_headers": response_headers,
            "response_body": response_body,
            "latency_ms": elapsed_ms,
            "error": error_msg,
        }
        log_id = await insert_replay_log(db_path, log_entry)
        await increment_replay_count(db_path, request_id)

        result = {
            "id": log_id,
            **log_entry,
        }

        await self._ws_manager.broadcast(
            channel_id,
            {
                "event": "replay_executed",
                "data": {
                    "request_id": request_id,
                    "replay_id": log_id,
                    "target_url": target_url,
                    "status_code": status_code,
                    "latency_ms": elapsed_ms,
                    "error": error_msg,
                },
            },
        )

        return result


# Default singleton instance
webhook_forwarder = WebhookForwarder()
