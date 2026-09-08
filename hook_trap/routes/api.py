import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hook_trap.config import settings
from hook_trap.database import (
    delete_channel_requests,
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
    """Save or update channel settings (e.g. auto-forwarding target URL)."""
    updated = await upsert_channel_config(
        db_path=settings.db_path,
        channel_id=channel_id,
        name=payload.name,
        auto_forward_url=payload.auto_forward_url,
    )
    return updated


@router.post("/verify-signature", response_model=SignatureVerifyResponse)
async def verify_signature(req: SignatureVerifyRequest) -> SignatureVerifyResponse:
    """
    Test and verify webhook HMAC signatures against raw payload.
    Supports Stripe, GitHub, Shopify, Svix, and generic HMAC-SHA256/SHA1.
    """
    provider = req.provider.lower().strip()
    secret_bytes = req.secret.encode("utf-8")
    payload_bytes = req.raw_payload.encode("utf-8")
    sig_header = req.signature_header.strip()

    if provider == "stripe":
        # Format: t=1614000000,v1=abc...,v0=...
        parts = {}
        for item in sig_header.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                parts.setdefault(k.strip(), []).append(v.strip())

        timestamps = parts.get("t", [])
        v1_signatures = parts.get("v1", [])
        if not timestamps or not v1_signatures:
            return SignatureVerifyResponse(
                valid=False,
                message="Missing t= or v1= parts in Stripe-Signature header",
                details={"parsed_parts": str(list(parts.keys()))},
            )

        ts = req.timestamp or timestamps[0]
        signed_payload = f"{ts}.".encode() + payload_bytes
        expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()

        matched = any(hmac.compare_digest(expected, s) for s in v1_signatures)
        return SignatureVerifyResponse(
            valid=matched,
            message="Stripe signature matched" if matched else "Stripe signature mismatch",
            details={"computed": expected, "provided": ", ".join(v1_signatures), "timestamp": ts},
        )

    elif provider == "github":
        # Format: sha256=abc... or sha1=...
        hash_func = hashlib.sha256
        prefix = "sha256="
        if sig_header.startswith("sha1="):
            hash_func = hashlib.sha1
            prefix = "sha1="

        provided_sig = sig_header.removeprefix(prefix)
        expected = hmac.new(secret_bytes, payload_bytes, hash_func).hexdigest()
        matched = hmac.compare_digest(expected, provided_sig)
        return SignatureVerifyResponse(
            valid=matched,
            message="GitHub signature matched" if matched else "GitHub signature mismatch",
            details={"computed": f"{prefix}{expected}", "provided": sig_header},
        )

    elif provider == "shopify":
        # Base64 encoded SHA256 HMAC
        import base64

        expected = base64.b64encode(
            hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
        ).decode("utf-8")
        matched = hmac.compare_digest(expected, sig_header)
        return SignatureVerifyResponse(
            valid=matched,
            message="Shopify signature matched" if matched else "Shopify signature mismatch",
            details={"computed": expected, "provided": sig_header},
        )

    else:
        # Generic SHA256 hex
        expected = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
        clean_sig = sig_header.lower()
        clean_sig = clean_sig.removeprefix("sha256=")
        matched = hmac.compare_digest(expected, clean_sig)
        return SignatureVerifyResponse(
            valid=matched,
            message="HMAC-SHA256 signature matched" if matched else "Signature mismatch",
            details={"computed": expected, "provided": clean_sig},
        )
