import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import init_db, insert_webhook_request
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_burst.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_burst_replay_endpoint_all_success(app_client):
    channel_id = "burst_test_chan"
    req_id = await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": channel_id,
            "method": "POST",
            "path": f"/catch/{channel_id}",
            "body_raw": '{"event": "payment.succeeded"}',
        },
    )

    mock_result = {
        "id": "log-burst",
        "request_id": req_id,
        "target_url": "http://localhost:5000/webhook",
        "status_code": 200,
        "response_headers": {},
        "response_body": '{"received": true}',
        "latency_ms": 12.5,
        "error": None,
    }

    with patch("hook_trap.routes.api.forward_request", new_callable=AsyncMock) as mock_forward:
        mock_forward.return_value = mock_result

        resp = await app_client.post(
            f"/api/channels/{channel_id}/requests/{req_id}/burst",
            json={
                "target_url": "http://localhost:5000/webhook",
                "count": 5,
                "concurrency": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["success_count"] == 5
        assert data["error_count"] == 0
        assert data["idempotency_verdict"] == "ALL_ACCEPTED"
        assert len(data["results"]) == 5
        assert mock_forward.call_count == 5


@pytest.mark.asyncio
async def test_burst_replay_suspected_race_condition(app_client):
    channel_id = "burst_race_chan"
    req_id = await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": channel_id,
            "method": "POST",
            "path": f"/catch/{channel_id}",
            "body_raw": '{"event": "stock.decrement"}',
        },
    )

    # First succeeds (200), subsequent calls return 500 error
    call_counter = 0

    async def side_effect_forward(**kwargs):
        nonlocal call_counter
        call_counter += 1
        status = 200 if call_counter == 1 else 500
        return {
            "id": f"log-{call_counter}",
            "request_id": req_id,
            "target_url": kwargs.get("target_url"),
            "status_code": status,
            "response_headers": {},
            "response_body": "Internal Error" if status == 500 else "OK",
            "latency_ms": 15.0,
            "error": "Server error" if status == 500 else None,
        }

    with patch("hook_trap.routes.api.forward_request", side_effect=side_effect_forward):
        resp = await app_client.post(
            f"/api/channels/{channel_id}/requests/{req_id}/burst",
            json={
                "target_url": "http://localhost:5000/webhook",
                "count": 4,
                "concurrency": 4,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert data["success_count"] == 1
        assert data["error_count"] == 3
        assert data["idempotency_verdict"] == "POTENTIAL_RACE_OR_CRASH"


@pytest.mark.asyncio
async def test_burst_replay_with_re_signing(app_client):
    channel_id = "burst_resign_chan"
    req_id = await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": channel_id,
            "method": "POST",
            "path": f"/catch/{channel_id}",
            "body_raw": '{"event": "order.created"}',
        },
    )

    with patch("hook_trap.routes.api.forward_request", new_callable=AsyncMock) as mock_forward:
        mock_forward.return_value = {
            "id": "log-resign",
            "request_id": req_id,
            "target_url": "http://localhost:5000/webhook",
            "status_code": 200,
            "response_headers": {},
            "response_body": "OK",
            "latency_ms": 10.0,
            "error": None,
        }

        resp = await app_client.post(
            f"/api/channels/{channel_id}/requests/{req_id}/burst",
            json={
                "target_url": "http://localhost:5000/webhook",
                "count": 2,
                "concurrency": 2,
                "re_sign": True,
                "signing_provider": "stripe",
                "signing_secret": "whsec_test_123",
            },
        )
        assert resp.status_code == 200
        assert mock_forward.call_count == 2

        for call in mock_forward.call_args_list:
            kwargs = call.kwargs
            assert kwargs["re_sign"] is True
            assert kwargs["signing_provider"] == "stripe"
            assert kwargs["signing_secret"] == "whsec_test_123"
