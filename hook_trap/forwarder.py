"""
Webhook forwarding facade providing backward-compatible functional interfaces.
Internally delegates to the object-oriented WebhookForwarder service.
"""

from typing import Any

from hook_trap.services.forwarder import (
    FILTERED_FORWARD_HEADERS,
    WebhookForwarder,
    webhook_forwarder,
)

__all__ = ["FILTERED_FORWARD_HEADERS", "WebhookForwarder", "forward_request", "webhook_forwarder"]


async def forward_request(
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
    return await webhook_forwarder.forward(
        db_path=db_path,
        channel_id=channel_id,
        request_id=request_id,
        target_url=target_url,
        timeout=timeout,
    )
