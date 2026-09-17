from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExportFormat(StrEnum):
    """Supported collection export formats."""

    POSTMAN = "postman"
    BRUNO = "bruno"
    JSON = "json"


class SignatureProvider(StrEnum):
    """Supported signature verification providers."""

    STRIPE = "stripe"
    GITHUB = "github"
    SHOPIFY = "shopify"
    SVIX = "svix"
    GENERIC_SHA256 = "generic_sha256"
    GENERIC_SHA1 = "generic_sha1"


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
    re_sign: bool = False
    signing_provider: str | None = None
    signing_secret: str | None = None


class BurstReplayRequest(BaseModel):
    """Payload to trigger concurrent burst replays for idempotency testing."""

    target_url: str
    count: int = Field(default=5, ge=1, le=50)
    concurrency: int = Field(default=5, ge=1, le=20)
    re_sign: bool = False
    signing_provider: str | None = None
    signing_secret: str | None = None


class BurstResultItem(BaseModel):
    """Individual result from a burst request."""

    index: int
    status_code: int | None = None
    latency_ms: float = 0.0
    error: str | None = None
    response_preview: str = ""


class BurstReplayResponse(BaseModel):
    """Aggregated outcome of a burst concurrency replay test."""

    target_url: str
    total: int
    success_count: int
    error_count: int
    avg_latency_ms: float
    status_distribution: dict[str, int] = Field(default_factory=dict)
    idempotency_verdict: str = "UNKNOWN"
    results: list[BurstResultItem] = Field(default_factory=list)


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
    max_requests: int = 500
    custom_response_mode: str = "default"
    custom_response_body: str | None = None
    custom_response_status: int = 200
    custom_response_content_type: str = "application/json"
    signing_secret: str | None = None
    signing_provider: str | None = None
    created_at: str
    updated_at: str


class ChannelConfigUpdate(BaseModel):
    """Request payload to update channel configuration."""

    name: str | None = None
    auto_forward_url: str | None = None
    max_requests: int | None = None
    custom_response_mode: str | None = None
    custom_response_body: str | None = None
    custom_response_status: int | None = None
    custom_response_content_type: str | None = None
    signing_secret: str | None = None
    signing_provider: str | None = None


class SignatureVerifyRequest(BaseModel):
    """Verification payload for webhook HMAC signatures."""

    provider: str
    secret: str
    signature_header: str
    raw_payload: str
    timestamp: str | None = None


class SignatureVerifyResponse(BaseModel):
    """Verification result with matched status and diagnostic details."""

    valid: bool
    message: str
    details: dict[str, str] = Field(default_factory=dict)


# --- Scenario Sequence Runner Models ---


class ScenarioStepCreate(BaseModel):
    """Payload to create a new step in a scenario sequence."""

    name: str
    method: str = "POST"
    path_suffix: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    payload_raw: str = ""
    expected_status: int = 200


class ScenarioStep(BaseModel):
    """Full detail of a scenario step."""

    id: str
    scenario_id: str
    step_order: int
    name: str
    method: str = "POST"
    path_suffix: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    payload_raw: str = ""
    expected_status: int = 200


class ScenarioCreate(BaseModel):
    """Payload to create a new webhook scenario."""

    channel_id: str
    name: str
    description: str | None = None
    target_url: str
    delay_between_steps_ms: int = 500
    steps: list[ScenarioStepCreate] = Field(default_factory=list)


class ScenarioUpdate(BaseModel):
    """Payload to update an existing scenario."""

    name: str | None = None
    description: str | None = None
    target_url: str | None = None
    delay_between_steps_ms: int | None = None
    steps: list[ScenarioStepCreate] | None = None


class Scenario(BaseModel):
    """Stored scenario entity with ordered steps."""

    id: str
    channel_id: str
    name: str
    description: str | None = None
    target_url: str
    delay_between_steps_ms: int = 500
    created_at: str
    steps: list[ScenarioStep] = Field(default_factory=list)


class ScenarioRunRequest(BaseModel):
    """Optional run parameter overrides."""

    target_url: str | None = None


class ScenarioStepResult(BaseModel):
    """Execution assertion result for a single scenario step."""

    step_id: str
    step_name: str
    step_order: int
    method: str
    url: str
    expected_status: int
    actual_status: int | None = None
    latency_ms: float = 0.0
    passed: bool
    response_body: str = ""
    error: str | None = None


class ScenarioRunResult(BaseModel):
    """Complete summary of a scenario sequence execution."""

    scenario_id: str
    scenario_name: str
    target_url: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    success: bool
    total_duration_ms: float
    step_results: list[ScenarioStepResult] = Field(default_factory=list)


# --- Payload Fuzzing Engine Models ---


class FuzzMutationType(StrEnum):
    """Supported payload mutation strategies."""

    MISSING_KEY = "missing_key"
    NULL_INJECTION = "null_injection"
    TYPE_CONFUSION = "type_confusion"
    CORRUPTED_SIGNATURE = "corrupted_signature"
    MALFORMED_JSON = "malformed_json"


class FuzzResilienceGrade(StrEnum):
    """Resilience grading evaluation."""

    PASSED = "PASSED"  # Graceful 4xx client rejection
    VULNERABLE = "VULNERABLE"  # Unhandled 5xx server crash or connection termination
    ACCEPTED = "ACCEPTED"  # 2xx accepted invalid / mutated input
    ERROR = "ERROR"  # Connection error / timeout


class FuzzingConfig(BaseModel):
    """Configuration options for payload fuzzing."""

    enabled_mutations: list[str] = Field(
        default_factory=lambda: [
            FuzzMutationType.MISSING_KEY,
            FuzzMutationType.NULL_INJECTION,
            FuzzMutationType.TYPE_CONFUSION,
            FuzzMutationType.CORRUPTED_SIGNATURE,
            FuzzMutationType.MALFORMED_JSON,
        ]
    )
    max_mutations: int = 25


class FuzzMutationCase(BaseModel):
    """A generated payload mutation test case."""

    case_id: str
    mutation_name: str
    mutation_type: str
    field_path: str | None = None
    description: str
    mutated_payload: str
    mutated_headers: dict[str, str] = Field(default_factory=dict)


class FuzzTestResult(BaseModel):
    """Result of executing a single mutated test case against the target."""

    case_id: str
    mutation_name: str
    mutation_type: str
    field_path: str | None = None
    description: str
    status_code: int | None = None
    latency_ms: float = 0.0
    resilience_grade: str
    passed: bool
    response_body: str = ""
    error: str | None = None


class FuzzRunRequest(BaseModel):
    """Payload to trigger payload fuzzing against a target URL."""

    target_url: str
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    payload_raw: str = ""
    config: FuzzingConfig = Field(default_factory=FuzzingConfig)
    timeout: float = 5.0
    channel_id: str | None = None


class FuzzRunResult(BaseModel):
    """Complete summary of a fuzzing test suite execution."""

    target_url: str
    total_cases: int
    passed_count: int
    vulnerable_count: int
    accepted_count: int
    error_count: int
    all_passed: bool
    summary: str
    cases: list[FuzzTestResult] = Field(default_factory=list)

