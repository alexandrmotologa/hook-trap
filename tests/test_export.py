import os

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import init_db, insert_webhook_request
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_export.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_export_postman_collection(app_client):
    # Insert sample request
    await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": "export_chan",
            "method": "POST",
            "path": "/catch/export_chan/v1/webhook",
            "headers": {"Content-Type": "application/json", "X-Token": "123"},
            "body_raw": '{"status": "active"}',
            "body_json": {"status": "active"},
        },
    )

    resp = await app_client.get("/api/channels/export_chan/export?format=postman")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["name"] == "hook-trap - export_chan"
    assert len(data["item"]) == 1
    req = data["item"][0]["request"]
    assert req["method"] == "POST"
    assert req["body"]["mode"] == "raw"
    assert "status" in req["body"]["raw"]


@pytest.mark.asyncio
async def test_export_bruno_collection(app_client):
    await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": "bruno_chan",
            "method": "GET",
            "path": "/catch/bruno_chan/ping",
            "headers": {},
            "body_raw": "",
        },
    )

    resp = await app_client.get("/api/channels/bruno_chan/export?format=bruno")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "hook-trap-bruno_chan"
    assert len(data["items"]) == 1
    assert data["items"][0]["request"]["method"] == "GET"


@pytest.mark.asyncio
async def test_export_json_dump(app_client):
    await insert_webhook_request(
        settings.db_path,
        {
            "channel_id": "json_chan",
            "method": "POST",
            "path": "/catch/json_chan",
            "body_raw": "payload",
        },
    )

    resp = await app_client.get("/api/channels/json_chan/export?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["body_raw"] == "payload"


@pytest.mark.asyncio
async def test_system_status_endpoint(app_client):
    resp = await app_client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "host" in data
    assert "port" in data


@pytest.mark.asyncio
async def test_channel_config_retention_update(app_client):
    resp = await app_client.put(
        "/api/channels/retention_chan/config",
        json={"name": "Test Ret", "max_requests": 250},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_requests"] == 250

    cfg_resp = await app_client.get("/api/channels/retention_chan/config")
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["max_requests"] == 250
