import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from hook_trap.config import settings
from hook_trap.database import (
    delete_channel_requests,
    get_all_channel_requests_for_export,
    get_channel_config,
    get_replay_logs_for_request,
    get_webhook_request_detail,
    get_webhook_requests,
    upsert_channel_config,
)
from hook_trap.forwarder import forward_request
from hook_trap.models import (
    ChannelConfigUpdate,
    ReplayRequest,
    SignatureVerifyRequest,
    SignatureVerifyResponse,
)
from hook_trap.services.export import export_service
from hook_trap.services.signatures import signature_verification_service

logger = logging.getLogger("hook_trap.api")

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/channels/{channel_id}/requests")
async def list_channel_requests(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    method: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Retrieve paginated summaries of webhooks captured for a channel."""
    items, total = await get_webhook_requests(
        settings.db_path,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
        method=method,
        search=search,
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/channels/{channel_id}/requests/{request_id}")
async def get_channel_request_detail(
    channel_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Retrieve detailed data for a specific captured webhook."""
    detail = await get_webhook_request_detail(settings.db_path, channel_id, request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Request not found")

    replays = await get_replay_logs_for_request(settings.db_path, request_id)
    detail["replays"] = replays
    return detail


@router.delete("/channels/{channel_id}/requests")
async def clear_channel_history(channel_id: str) -> dict[str, Any]:
    """Clear all captured webhooks and replay logs for a channel."""
    deleted_count = await delete_channel_requests(settings.db_path, channel_id)
    return {"status": "cleared", "channel_id": channel_id, "deleted_count": deleted_count}


@router.post("/channels/{channel_id}/requests/{request_id}/replay")
async def replay_webhook_request(
    channel_id: str,
    request_id: str,
    payload: ReplayRequest,
) -> dict[str, Any]:
    """Execute an HTTP replay to the specified target URL."""
    try:
        result = await forward_request(
            db_path=settings.db_path,
            channel_id=channel_id,
            request_id=request_id,
            target_url=payload.target_url,
            timeout=settings.replay_timeout,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replay execution failed: {exc}")


@router.get("/channels/{channel_id}/config")
async def get_channel_configuration(channel_id: str) -> dict[str, Any]:
    """Get settings for a channel."""
    cfg = await get_channel_config(settings.db_path, channel_id)
    if not cfg:
        return {
            "channel_id": channel_id,
            "name": None,
            "auto_forward_url": settings.default_auto_forward_url,
            "created_at": None,
            "updated_at": None,
        }
    return cfg


@router.put("/channels/{channel_id}/config")
async def update_channel_configuration(
    channel_id: str,
    payload: ChannelConfigUpdate,
) -> dict[str, Any]:
    """Save or update channel settings (e.g. auto-forwarding target URL, max requests)."""
    updated = await upsert_channel_config(
        db_path=settings.db_path,
        channel_id=channel_id,
        name=payload.name,
        auto_forward_url=payload.auto_forward_url,
        max_requests=payload.max_requests,
    )
    return updated


@router.get("/channels/{channel_id}/export")
async def export_channel_collection(
    channel_id: str,
    format: str = Query("postman", pattern="^(postman|bruno|json)$"),
) -> Response:
    """Export captured webhooks as a Postman Collection v2.1, Bruno, or JSON dump."""
    requests = await get_all_channel_requests_for_export(settings.db_path, channel_id)
    base_url = f"http://{settings.host}:{settings.port}"
    return export_service.export(
        format_name=format,
        channel_id=channel_id,
        requests=requests,
        base_url=base_url,
    )


@router.get("/system/status")
async def system_status() -> dict[str, Any]:
    """Retrieve runtime system info including active public tunnel URL if present."""
    return {
        "version": "0.1.0",
        "host": settings.host,
        "port": settings.port,
        "public_tunnel_url": settings.public_tunnel_url,
    }


@router.post("/verify-signature", response_model=SignatureVerifyResponse)
async def verify_signature(req: SignatureVerifyRequest) -> SignatureVerifyResponse:
    """
    Test and verify webhook HMAC signatures against raw payload.
    Supports Stripe, GitHub, Shopify, Svix, and generic HMAC-SHA256/SHA1.
    """
    return signature_verification_service.verify(req)
