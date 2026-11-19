import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from hook_trap import __version__
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
    BurstReplayRequest,
    BurstReplayResponse,
    BurstResultItem,
    ChannelConfigUpdate,
    ReplayRequest,
    SignatureVerifyRequest,
    SignatureVerifyResponse,
)
from hook_trap.services.export import (
    export_service,
    generate_curl_snippet,
    generate_javascript_snippet,
    generate_jest_snippet,
    generate_pytest_snippet,
    generate_python_snippet,
)
from hook_trap.services.samples import SAMPLE_TEMPLATES, get_sample_template
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
            re_sign=payload.re_sign,
            signing_provider=payload.signing_provider,
            signing_secret=payload.signing_secret,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replay execution failed: {exc}")


@router.post(
    "/channels/{channel_id}/requests/{request_id}/burst",
    response_model=BurstReplayResponse,
)
async def burst_replay_webhook_request(
    channel_id: str,
    request_id: str,
    payload: BurstReplayRequest,
) -> BurstReplayResponse:
    """Execute concurrent burst replays of a webhook for idempotency and race condition testing."""
    req_detail = await get_webhook_request_detail(settings.db_path, channel_id, request_id)
    if not req_detail:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    sem = asyncio.Semaphore(payload.concurrency)

    async def _single_replay(idx: int) -> BurstResultItem:
        async with sem:
            try:
                res = await forward_request(
                    db_path=settings.db_path,
                    channel_id=channel_id,
                    request_id=request_id,
                    target_url=payload.target_url,
                    timeout=settings.replay_timeout,
                    re_sign=payload.re_sign,
                    signing_provider=payload.signing_provider,
                    signing_secret=payload.signing_secret,
                )
                status = res.get("status_code")
                error = res.get("error")
                body_prev = (res.get("response_body") or "")[:200]
                lat = res.get("latency_ms", 0.0)
                return BurstResultItem(
                    index=idx,
                    status_code=status,
                    latency_ms=lat,
                    error=error,
                    response_preview=body_prev,
                )
            except Exception as exc:
                return BurstResultItem(
                    index=idx,
                    status_code=None,
                    latency_ms=0.0,
                    error=str(exc),
                    response_preview="",
                )

    tasks = [_single_replay(i + 1) for i in range(payload.count)]
    results: list[BurstResultItem] = await asyncio.gather(*tasks)

    status_distribution: dict[str, int] = {}
    success_count = 0
    error_count = 0
    total_lat = 0.0

    for r in results:
        total_lat += r.latency_ms
        if r.error or (r.status_code and r.status_code >= 500):
            error_count += 1
        elif r.status_code and 200 <= r.status_code < 300:
            success_count += 1

        key = str(r.status_code) if r.status_code is not None else "ERROR"
        status_distribution[key] = status_distribution.get(key, 0) + 1

    avg_lat = round(total_lat / len(results), 2) if results else 0.0

    if error_count > 0:
        verdict = "POTENTIAL_RACE_OR_CRASH"
    elif success_count == len(results):
        verdict = "ALL_ACCEPTED"
    elif success_count >= 1:
        verdict = "IDEMPOTENT_HANDLED"
    else:
        verdict = "ALL_FAILED"

    return BurstReplayResponse(
        target_url=payload.target_url,
        total=payload.count,
        success_count=success_count,
        error_count=error_count,
        avg_latency_ms=avg_lat,
        status_distribution=status_distribution,
        idempotency_verdict=verdict,
        results=results,
    )


@router.get("/channels/{channel_id}/config")
async def get_channel_configuration(channel_id: str) -> dict[str, Any]:
    """Get settings for a channel."""
    cfg = await get_channel_config(settings.db_path, channel_id)
    if not cfg:
        return {
            "channel_id": channel_id,
            "name": None,
            "auto_forward_url": settings.default_auto_forward_url,
            "custom_response_mode": "default",
            "custom_response_body": None,
            "custom_response_status": 200,
            "custom_response_content_type": "application/json",
            "signing_secret": None,
            "signing_provider": None,
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
        custom_response_mode=payload.custom_response_mode,
        custom_response_body=payload.custom_response_body,
        custom_response_status=payload.custom_response_status,
        custom_response_content_type=payload.custom_response_content_type,
        signing_secret=payload.signing_secret,
        signing_provider=payload.signing_provider,
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


@router.get("/channels/{channel_id}/requests/{request_id}/snippet")
async def get_request_snippet(
    channel_id: str,
    request_id: str,
    format: str = Query("curl", pattern="^(curl|python|javascript|pytest|jest)$"),
    target_url: str | None = None,
) -> dict[str, str]:
    """Generate reproducible code snippet (cURL, Python, JS, Pytest, Jest) for a request."""
    detail = await get_webhook_request_detail(settings.db_path, channel_id, request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Request not found")

    target = target_url or f"http://{settings.host}:{settings.port}/catch/{channel_id}"
    method = detail.get("method", "POST")
    headers = detail.get("headers", {})
    body_raw = detail.get("body_raw", "")
    body_json = detail.get("body_json")

    if format == "curl":
        code = generate_curl_snippet(method, target, headers, body_raw)
    elif format == "python":
        code = generate_python_snippet(method, target, headers, body_raw)
    elif format == "javascript":
        code = generate_javascript_snippet(method, target, headers, body_raw)
    elif format == "pytest":
        code = generate_pytest_snippet(method, target, headers, body_raw, body_json)
    elif format == "jest":
        code = generate_jest_snippet(method, target, headers, body_raw, body_json)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported snippet format: {format}")

    return {"format": format, "target_url": target, "code": code}


@router.get("/samples")
async def list_sample_templates() -> dict[str, Any]:
    """List available sample webhook presets for rapid testing."""
    return {
        "presets": [
            {
                "key": k,
                "provider": v.get("provider"),
                "description": v.get("description"),
                "subpath": v.get("subpath"),
            }
            for k, v in SAMPLE_TEMPLATES.items()
        ]
    }


@router.post("/channels/{channel_id}/trigger")
async def trigger_sample_webhook(
    channel_id: str,
    provider: str = Query("stripe-payment", description="Sample template key"),
) -> dict[str, Any]:
    """Inject a realistic synthetic webhook payload into the channel."""
    import httpx

    template = get_sample_template(provider)
    subpath = template.get("subpath", "")
    target = f"http://{settings.host}:{settings.port}/catch/{channel_id}"
    if subpath:
        target = f"{target}/{subpath}"

    headers = dict(template.get("headers", {}))
    body = template.get("body", {})

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(target, json=body, headers=headers)
        try:
            resp_data = resp.json()
        except Exception:
            resp_data = resp.text

        return {
            "status": "triggered",
            "provider": provider,
            "target": target,
            "response_status": resp.status_code,
            "response": resp_data,
        }


@router.get("/system/status")
async def system_status() -> dict[str, Any]:
    """Retrieve runtime system info including active public tunnel URL if present."""
    return {
        "version": __version__,
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
