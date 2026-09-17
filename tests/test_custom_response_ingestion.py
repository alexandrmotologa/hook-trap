import os

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.config import settings
from hook_trap.database import init_db, upsert_channel_config
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_custom_resp.db")
    settings.db_path = db_path
    await init_db(db_path)

    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_slack_challenge_handshake(app_client):
    channel_id = "slack_handshake_chan"
    # Configure channel for echo_challenge
    await upsert_channel_config(
        settings.db_path,
        channel_id=channel_id,
        custom_response_mode="echo_challenge",
    )

    slack_payload = {
        "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl",
        "challenge": "3eZbrw1aBm2rZg RN4nBq8n5bFiwAGCr38CQBxBKqtok",
        "type": "url_verification",
    }
    response = await app_client.post(
        f"/catch/{channel_id}",
        json=slack_payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {"challenge": slack_payload["challenge"]}


@pytest.mark.asyncio
async def test_meta_whatsapp_challenge_handshake(app_client):
    channel_id = "meta_handshake_chan"
    # Configure channel for echo_challenge
    await upsert_channel_config(
        settings.db_path,
        channel_id=channel_id,
        custom_response_mode="echo_challenge",
    )

    challenge_token = "1158201444"
    response = await app_client.get(
        f"/catch/{channel_id}?hub.mode=subscribe&hub.challenge={challenge_token}&hub.verify_token=my_secret"
    )
    assert response.status_code == 200
    assert response.text == challenge_token


@pytest.mark.asyncio
async def test_custom_json_response(app_client):
    channel_id = "custom_json_chan"
    custom_body = '{"received": true, "worker": "cluster-1"}'
    await upsert_channel_config(
        settings.db_path,
        channel_id=channel_id,
        custom_response_mode="custom_json",
        custom_response_body=custom_body,
        custom_response_status=202,
    )

    response = await app_client.post(
        f"/catch/{channel_id}",
        json={"event": "order.created"},
    )
    assert response.status_code == 202
    assert response.headers.get("content-type", "").startswith("application/json")
    data = response.json()
    assert data == {"received": True, "worker": "cluster-1"}


@pytest.mark.asyncio
async def test_custom_text_or_xml_response(app_client):
    channel_id = "custom_xml_chan"
    xml_body = "<Response><Message>Thanks</Message></Response>"
    await upsert_channel_config(
        settings.db_path,
        channel_id=channel_id,
        custom_response_mode="custom_text",
        custom_response_body=xml_body,
        custom_response_status=200,
        custom_response_content_type="application/xml",
    )

    response = await app_client.post(
        f"/catch/{channel_id}",
        content=b"From=+123456789&Body=Hello",
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers.get("content-type", "")
    assert response.text == xml_body
