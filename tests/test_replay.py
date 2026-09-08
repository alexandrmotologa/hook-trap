import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import (
    get_replay_logs_for_request,
    get_webhook_request_detail,
    init_db,
    insert_webhook_request,
)
from hook_trap.forwarder import forward_request
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_replay.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_forward_request_execution(tmp_path):
    db_path = str(tmp_path / "test_forward.db")
    await init_db(db_path)

    req_id = await insert_webhook_request(
        db_path,
        {
            "channel_id": "test_fwd",
            "method": "POST",
            "path": "/catch/test_fwd",
            "body_raw": '{"ping": "pong"}',
            "headers": {
                "Host": "hook-trap.local",
                "X-Custom-Header": "KeepThis",
                "Content-Type": "application/json",
            },
        },
    )

    mock_response = httpx.Response(
        status_code=200,
        text='{"received": true}',
        headers={"Content-Type": "application/json"},
        request=httpx.Request("POST", "http://localhost:3000/webhook"),
    )

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_response

        result = await forward_request(
            db_path=db_path,
            channel_id="test_fwd",
            request_id=req_id,
            target_url="http://localhost:3000/webhook",
        )

        assert result["status_code"] == 200
        assert result["response_body"] == '{"received": true}'
        assert result["latency_ms"] >= 0.0

        # Verify host header was stripped, custom header preserved
        call_kwargs = mock_request.call_args.kwargs
        headers_sent = call_kwargs["headers"]
        assert "Host" not in headers_sent
        assert "X-Custom-Header" in headers_sent

        # Check logs saved in DB
        logs = await get_replay_logs_for_request(db_path, req_id)
        assert len(logs) == 1
        assert logs[0]["status_code"] == 200

        # Check replay count incremented
        detail = await get_webhook_request_detail(db_path, "test_fwd", req_id)
        assert detail["replay_count"] == 1


@pytest.mark.asyncio
async def test_api_replay_endpoint(app_client):
    req_id = await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": "api_replay_chan",
            "method": "POST",
            "path": "/catch/api_replay_chan",
            "body_raw": "sample",
        },
    )

    mock_result = {
        "id": "log-123",
        "request_id": req_id,
        "target_url": "http://localhost:4000/webhook",
        "status_code": 204,
        "response_headers": {},
        "response_body": "",
        "latency_ms": 15.2,
        "error": None,
    }

    with patch("hook_trap.routes.api.forward_request", new_callable=AsyncMock) as mock_forward:
        mock_forward.return_value = mock_result

        resp = await app_client.post(
            f"/api/channels/api_replay_chan/requests/{req_id}/replay",
            json={"target_url": "http://localhost:4000/webhook"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_code"] == 204
        assert data["id"] == "log-123"
