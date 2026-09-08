import os

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import get_webhook_request_detail, init_db
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_catch.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_catch_post_json(app_client):
    payload = {"event": "payment_intent.succeeded", "amount": 4200}
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": "t=1600000000,v1=98765abcdef",
    }
    response = await app_client.post(
        "/catch/stripe_test",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "captured"
    assert data["channel"] == "stripe_test"
    req_id = data["id"]

    # Verify captured in database
    detail = await get_webhook_request_detail(settings.db_path, "stripe_test", req_id)
    assert detail is not None
    assert detail["method"] == "POST"
    assert detail["body_json"] == payload
    assert detail["headers"]["stripe-signature"] == "t=1600000000,v1=98765abcdef"


@pytest.mark.asyncio
async def test_catch_subpath_and_query_params(app_client):
    response = await app_client.get(
        "/catch/gh_chan/webhook/events?ref=main&sender=octocat",
        headers={"User-Agent": "GitHub-Hookshot/1.0"},
    )
    assert response.status_code == 200
    data = response.json()
    req_id = data["id"]

    detail = await get_webhook_request_detail(settings.db_path, "gh_chan", req_id)
    assert detail is not None
    assert detail["method"] == "GET"
    assert detail["path"] == "/catch/gh_chan/webhook/events"
    assert detail["query_params"]["ref"] == "main"
    assert detail["query_params"]["sender"] == "octocat"


@pytest.mark.asyncio
async def test_catch_binary_payload(app_client):
    raw_bytes = b"\x00\x01\x02\x03\xff\xfe\xfd"
    response = await app_client.post(
        "/catch/binary_chan",
        content=raw_bytes,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    req_id = response.json()["id"]

    detail = await get_webhook_request_detail(settings.db_path, "binary_chan", req_id)
    assert detail is not None
    assert detail["content_type"] == "application/octet-stream"
    assert len(detail["body_raw"]) > 0


@pytest.mark.asyncio
async def test_catch_custom_status_override(app_client):
    # Tests upstream retry simulation via ?status=503
    response = await app_client.post(
        "/catch/retry_test?status=503",
        json={"test": "retry"},
    )
    assert response.status_code == 503
    assert response.json()["status"] == "captured"
