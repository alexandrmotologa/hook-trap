from typing import Any

from pydantic import BaseModel, Field


class WebhookRequestSummary(BaseModel):
    """Compact summary of a captured webhook request for list views."""

    id: str
    channel_id: str
    timestamp: str
    method: str
    path: str
    content_type: str | None = None
    client_ip: str | None = None
    replay_count: int = 0
    body_size: int = 0
    body_preview: str = ""


class WebhookRequestDetail(BaseModel):
    """Full details of a captured webhook request."""

    id: str
    channel_id: str
    timestamp: str
    method: str
    path: str
    query_params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body_raw: str = ""
    body_json: Any | None = None
    content_type: str | None = None
    client_ip: str | None = None
    replay_count: int = 0


class ReplayRequest(BaseModel):
    """Payload to trigger an HTTP replay to a target URL."""

    target_url: str


class ReplayLogDetail(BaseModel):
    """Result of an HTTP replay execution."""

    id: str
    request_id: str
    target_url: str
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    latency_ms: float = 0.0
    created_at: str
    error: str | None = None


class ChannelConfig(BaseModel):
    """Configuration associated with a channel."""

    channel_id: str
    name: str | None = None
    auto_forward_url: str | None = None
    created_at: str
    updated_at: str


class ChannelConfigUpdate(BaseModel):
    """Request payload to update channel configuration."""

    name: str | None = None
    auto_forward_url: str | None = None


class SignatureVerifyRequest(BaseModel):
    """Verification payload for common webhook HMAC signatures."""

    provider: str  # "stripe", "github", "shopify", "svix", "generic_sha256", "generic_sha1"
    secret: str
    signature_header: str
    raw_payload: str
    timestamp: str | None = None  # Needed for stripe (t=...) or svix (webhook-timestamp)


class SignatureVerifyResponse(BaseModel):
    """Verification result."""

    valid: bool
    message: str
    details: dict[str, str] = Field(default_factory=dict)
