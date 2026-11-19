import os

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import init_db, insert_webhook_request
from hook_trap.server import create_app
from hook_trap.services.export import (
    generate_curl_snippet,
    generate_javascript_snippet,
    generate_jest_snippet,
    generate_pytest_snippet,
    generate_python_snippet,
)
from hook_trap.services.samples import get_sample_template


def test_curl_generator():
    headers = {"Content-Type": "application/json", "Authorization": "Bearer 123"}
    snippet = generate_curl_snippet(
        "POST", "http://localhost:3000/webhook", headers, '{"ok": true}'
    )
    assert 'curl -X POST "http://localhost:3000/webhook"' in snippet
    assert '-H "Content-Type: application/json"' in snippet
    assert '-H "Authorization: Bearer 123"' in snippet
    assert "--data '{\"ok\": true}'" in snippet


def test_python_generator():
    headers = {"Content-Type": "application/json"}
    snippet = generate_python_snippet(
        "POST", "http://localhost:3000/webhook", headers, '{"ping": 1}'
    )
    assert "import httpx" in snippet
    assert 'url = "http://localhost:3000/webhook"' in snippet
    assert "response = httpx.post(url, headers=headers, content=data)" in snippet


def test_javascript_generator():
    headers = {"Content-Type": "application/json"}
    snippet = generate_javascript_snippet(
        "POST", "http://localhost:3000/webhook", headers, '{"ping": 1}'
    )
    assert 'fetch("http://localhost:3000/webhook"' in snippet
    assert 'method: "POST"' in snippet


def test_pytest_generator():
    headers = {"Content-Type": "application/json"}
    snippet = generate_pytest_snippet(
        "POST", "http://localhost:3000/webhook", headers, '{"a": 1}', {"a": 1}
    )
    assert "@pytest.mark.asyncio" in snippet
    assert "async def test_webhook_handler():" in snippet
    assert "assert response.status_code == 200" in snippet


def test_jest_generator():
    headers = {"Content-Type": "application/json"}
    snippet = generate_jest_snippet(
        "POST", "http://localhost:3000/webhook", headers, '{"a": 1}', {"a": 1}
    )
    assert 'describe("Webhook Receiver Regression"' in snippet
    assert "expect(response.status).toBe(200);" in snippet


def test_sample_templates_lookup():
    stripe = get_sample_template("stripe-payment")
    assert stripe["provider"] == "stripe"
    assert "payment_intent.succeeded" in str(stripe["body"])

    github = get_sample_template("github")
    assert github["provider"] == "github"

    fallback = get_sample_template("unknown-template-xyz")
    assert fallback["provider"] == "stripe"


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_snippets.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_api_snippet_endpoint(app_client):
    req_id = await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": "snip_chan",
            "method": "POST",
            "path": "/catch/snip_chan",
            "headers": {"Content-Type": "application/json"},
            "body_raw": '{"status": "ok"}',
            "body_json": {"status": "ok"},
        },
    )

    # cURL snippet
    resp = await app_client.get(
        f"/api/channels/snip_chan/requests/{req_id}/snippet?format=curl&target_url=http://api.local/hook"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "curl"
    assert 'curl -X POST "http://api.local/hook"' in data["code"]

    # Python snippet
    resp = await app_client.get(
        f"/api/channels/snip_chan/requests/{req_id}/snippet?format=python&target_url=http://api.local/hook"
    )
    assert resp.status_code == 200
    assert "httpx.post" in resp.json()["code"]

    # Jest snippet
    resp = await app_client.get(
        f"/api/channels/snip_chan/requests/{req_id}/snippet?format=jest&target_url=http://api.local/hook"
    )
    assert resp.status_code == 200
    assert "describe(" in resp.json()["code"]


@pytest.mark.asyncio
async def test_api_samples_list(app_client):
    resp = await app_client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert "presets" in data
    assert len(data["presets"]) >= 5
    keys = [p["key"] for p in data["presets"]]
    assert "stripe-payment" in keys
    assert "github-push" in keys
