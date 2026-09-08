import base64
import json
import logging
from typing import Any

from fastapi import BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from hook_trap.database import (
    get_channel_config,
    insert_webhook_request,
    prune_channel_requests,
)
from hook_trap.services.forwarder import WebhookForwarder, webhook_forwarder
from hook_trap.ws_manager import ConnectionManager, ws_manager

logger = logging.getLogger("hook_trap.ingestion")


class WebhookIngestionService:
    """Encapsulates webhook capture, decoding, persistence, broadcast, and task scheduling."""

    def __init__(
        self,
        connection_manager: ConnectionManager | None = None,
        forwarder: WebhookForwarder | None = None,
    ) -> None:
        self._ws_manager = connection_manager or ws_manager
        self._forwarder = forwarder or webhook_forwarder

    async def ingest(
        self,
        channel_id: str,
        subpath: str,
        request: Request,
        background_tasks: BackgroundTasks,
        db_path: str,
        default_auto_forward_url: str | None = None,
        replay_timeout: float = 10.0,
    ) -> Response:
        """Process incoming webhook HTTP request and persist captured data."""
        # 1. Capture raw payload bytes
        body_bytes = await request.body()

        # 2. Determine text vs binary encoding
        is_binary = False
        try:
            body_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            is_binary = True
            body_text = base64.b64encode(body_bytes).decode("ascii")

        # 3. Attempt JSON parse if text
        body_json = None
        if not is_binary and body_text:
            try:
                body_json = json.loads(body_text)
            except Exception:
                body_json = None

        # 4. Extract headers and query parameters
        headers_dict = dict(request.headers)
        query_params_dict = dict(request.query_params)

        # 5. Determine client IP
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "127.0.0.1"
        )

        # 6. Format path
        full_path = f"/catch/{channel_id}"
        if subpath:
            full_path = f"{full_path}/{subpath}"

        content_type = request.headers.get("content-type")

        # 7. Persist to database
        record_data: dict[str, Any] = {
            "channel_id": channel_id,
            "method": request.method,
            "path": full_path,
            "query_params": query_params_dict,
            "headers": headers_dict,
            "body_raw": body_text,
            "body_json": body_json,
            "content_type": content_type,
            "client_ip": client_ip,
            "replay_count": 0,
        }
        req_id = await insert_webhook_request(db_path, record_data)

        # 8. Broadcast real-time event to active WebSocket clients
        await self._ws_manager.broadcast(
            channel_id,
            {
                "event": "new_request",
                "data": {
                    "id": req_id,
                    "channel_id": channel_id,
                    "timestamp": record_data.get("timestamp"),
                    "method": request.method,
                    "path": full_path,
                    "headers": headers_dict,
                    "body": body_json if body_json is not None else body_text[:500],
                    "body_size": len(body_bytes),
                    "content_type": content_type,
                    "client_ip": client_ip,
                },
            },
        )

        # 9. Check auto-forwarding & channel retention configuration
        channel_cfg = await get_channel_config(db_path, channel_id)
        auto_forward_target = None
        max_requests = 500
        if channel_cfg:
            auto_forward_target = channel_cfg.get("auto_forward_url")
            max_requests = channel_cfg.get("max_requests") or 500
        elif default_auto_forward_url:
            auto_forward_target = default_auto_forward_url

        if auto_forward_target:
            background_tasks.add_task(
                self._forwarder.forward,
                db_path,
                channel_id,
                req_id,
                auto_forward_target,
                replay_timeout,
            )

        background_tasks.add_task(
            prune_channel_requests,
            db_path,
            channel_id,
            max_requests,
        )

        # 10. Check for custom status response override (?status=503)
        status_code = 200
        if "status" in query_params_dict:
            try:
                status_code = int(query_params_dict["status"])
            except ValueError:
                pass

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "captured",
                "id": req_id,
                "channel": channel_id,
                "method": request.method,
                "size_bytes": len(body_bytes),
            },
        )


# Default singleton instance
webhook_ingestion_service = WebhookIngestionService()
