import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from hook_trap.config import settings
from hook_trap.database import (
    get_channel_config,
    insert_webhook_request,
)
from hook_trap.forwarder import forward_request
from hook_trap.ws_manager import ws_manager

logger = logging.getLogger("hook_trap.catch")

router = APIRouter(tags=["Ingestion"])


async def _handle_ingestion(
    channel_id: str,
    subpath: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Core webhook ingestion handler for /catch/{channel_id} routes."""
    # Capture raw body bytes
    body_bytes = await request.body()

    # Determine if body is valid UTF-8 text or binary
    is_binary = False
    try:
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        is_binary = True
        body_text = base64.b64encode(body_bytes).decode("ascii")

    # Try parsing JSON if text
    body_json = None
    if not is_binary and body_text:
        try:
            body_json = json.loads(body_text)
        except Exception:
            body_json = None

    # Collect headers preserving incoming names
    headers_dict = dict(request.headers)

    # Client IP
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )

    # Query params
    query_params_dict = dict(request.query_params)

    # Full relative path
    full_path = f"/catch/{channel_id}"
    if subpath:
        full_path = f"{full_path}/{subpath}"

    content_type = request.headers.get("content-type")

    # Save to SQLite
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

    req_id = await insert_webhook_request(settings.db_path, record_data)

    # Broadcast event via WebSocket
    broadcast_payload = {
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
    }
    await ws_manager.broadcast(channel_id, broadcast_payload)

    # Check for auto-forwarding configuration
    channel_cfg = await get_channel_config(settings.db_path, channel_id)
    auto_forward_target = None
    if channel_cfg and channel_cfg.get("auto_forward_url"):
        auto_forward_target = channel_cfg["auto_forward_url"]
    elif settings.default_auto_forward_url:
        auto_forward_target = settings.default_auto_forward_url

    if auto_forward_target:
        background_tasks.add_task(
            forward_request,
            settings.db_path,
            channel_id,
            req_id,
            auto_forward_target,
            settings.replay_timeout,
        )

    # Allow custom status response override via query param for testing upstream retries
    status_code = 200
    if "status" in query_params_dict:
        try:
            status_code = int(query_params_dict["status"])
        except ValueError:
            pass

    response_content = {
        "status": "captured",
        "id": req_id,
        "channel": channel_id,
        "method": request.method,
        "size_bytes": len(body_bytes),
    }

    return JSONResponse(status_code=status_code, content=response_content)


@router.api_route(
    "/catch/{channel_id}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def catch_root(
    channel_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Capture webhook sent to channel root."""
    return await _handle_ingestion(channel_id, "", request, background_tasks)


@router.api_route(
    "/catch/{channel_id}/{subpath:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def catch_subpath(
    channel_id: str,
    subpath: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Capture webhook sent to channel with arbitrary subpath."""
    return await _handle_ingestion(channel_id, subpath, request, background_tasks)
