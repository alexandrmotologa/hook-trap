import hashlib
import hmac

import pytest
from fastapi import HTTPException

from hook_trap.models import ExportFormat, SignatureProvider, SignatureVerifyRequest
from hook_trap.services.export import (
    ExportService,
)
from hook_trap.services.forwarder import WebhookForwarder
from hook_trap.services.signatures import (
    SignatureVerificationService,
)
from hook_trap.services.tunnel import TunnelManager


def test_signature_verification_strategies():
    service = SignatureVerificationService()

    # Generic SHA256
    secret = "secret123"
    raw_payload = '{"event": "ping"}'
    expected_sig = hmac.new(secret.encode(), raw_payload.encode(), hashlib.sha256).hexdigest()

    req = SignatureVerifyRequest(
        provider=SignatureProvider.GENERIC_SHA256,
        raw_payload=raw_payload,
        secret=secret,
        signature_header=f"sha256={expected_sig}",
    )
    res = service.verify(req)
    assert res.valid is True

    # Generic SHA1
    req_sha1 = SignatureVerifyRequest(
        provider=SignatureProvider.GENERIC_SHA1,
        raw_payload='{"ping": true}',
        secret="key",
        signature_header="invalid_sig",
    )
    res_sha1 = service.verify(req_sha1)
    assert res_sha1.valid is False

    # Stripe invalid header format
    req_stripe_invalid = SignatureVerifyRequest(
        provider=SignatureProvider.STRIPE,
        raw_payload='{"id": "evt_1"}',
        secret="whsec_test",
        signature_header="malformed_header",
    )
    res_stripe_invalid = service.verify(req_stripe_invalid)
    assert res_stripe_invalid.valid is False


def test_export_service_and_strategies():
    service = ExportService()

    sample_requests = [
        {
            "id": "req-1",
            "method": "POST",
            "path": "/catch/c1/event",
            "timestamp": "2026-03-08T20:00:00Z",
            "headers": {"content-type": "application/json", "host": "evil.com"},
            "body_raw": '{"test": 1}',
            "body_json": {"test": 1},
        }
    ]

    # Postman
    resp_postman = service.export(
        ExportFormat.POSTMAN, "c1", sample_requests, "http://localhost:8080"
    )
    assert resp_postman.status_code == 200
    assert "hook-trap-c1-postman.json" in resp_postman.headers["content-disposition"]

    # Bruno
    resp_bruno = service.export(ExportFormat.BRUNO, "c1", sample_requests, "http://localhost:8080")
    assert resp_bruno.status_code == 200
    assert "hook-trap-c1-bruno.json" in resp_bruno.headers["content-disposition"]

    # JSON
    resp_json = service.export(ExportFormat.JSON, "c1", sample_requests, "http://localhost:8080")
    assert resp_json.status_code == 200
    assert "hook-trap-c1.json" in resp_json.headers["content-disposition"]

    # Unsupported format
    with pytest.raises(HTTPException) as exc_info:
        service.export("unknown_format", "c1", sample_requests, "http://localhost:8080")
    assert exc_info.value.status_code == 400


def test_webhook_forwarder_header_filtering():
    forwarder = WebhookForwarder()
    incoming = {
        "Host": "localhost:8080",
        "Content-Length": "123",
        "Connection": "keep-alive",
        "X-Custom-Header": "Webhook-Trap",
        "Authorization": "Bearer token123",
    }
    filtered = forwarder.filter_headers(incoming)
    assert "X-Custom-Header" in filtered
    assert "Authorization" in filtered
    assert "Host" not in filtered
    assert "Content-Length" not in filtered
    assert "Connection" not in filtered


def test_tunnel_manager_defaults():
    mgr = TunnelManager()
    assert mgr.process is None
    assert mgr.public_url is None
    # Stopping when inactive should be safe no-op
    mgr.stop()
    assert mgr.public_url is None
