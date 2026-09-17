from hook_trap.services.export.test_generators import (
    generate_jest_snippet,
    generate_pytest_snippet,
)


def test_generate_pytest_snippet_with_json():
    snippet = generate_pytest_snippet(
        method="POST",
        target_url="http://localhost:8000/webhook",
        headers={"Content-Type": "application/json", "X-Custom-Header": "value123"},
        body_raw='{"event": "charge.succeeded"}',
        body_json={"event": "charge.succeeded"},
    )

    assert "import pytest" in snippet
    assert "import httpx" in snippet
    assert "async def test_webhook_handler():" in snippet
    assert 'url = "http://localhost:8000/webhook"' in snippet
    assert '"X-Custom-Header": "value123"' in snippet
    assert "json=payload" in snippet
    assert "assert response.status_code == 200" in snippet


def test_generate_pytest_snippet_with_raw_text():
    snippet = generate_pytest_snippet(
        method="PUT",
        target_url="http://localhost:8000/raw",
        headers={"Content-Type": "text/plain"},
        body_raw="plain text payload",
        body_json=None,
    )

    assert "content=payload" in snippet
    assert 'client.request("PUT", url' in snippet
    assert "assert response.status_code == 200" in snippet


def test_generate_jest_snippet_with_json():
    snippet = generate_jest_snippet(
        method="POST",
        target_url="http://localhost:3000/api/webhook",
        headers={"Content-Type": "application/json", "Stripe-Signature": "t=123,v1=abc"},
        body_raw='{"id": "evt_123"}',
        body_json={"id": "evt_123"},
    )

    assert 'import { describe, it, expect } from "vitest"' in snippet
    assert 'describe("Webhook Receiver Regression"' in snippet
    assert 'method: "POST"' in snippet
    assert '"Stripe-Signature": "t=123,v1=abc"' in snippet
    assert "expect(response.status).toBe(200)" in snippet
