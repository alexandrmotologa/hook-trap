import os

import pytest
from fastapi.testclient import TestClient

from hook_trap.config import settings
from hook_trap.database import init_db
from hook_trap.server import create_app


@pytest.fixture
def sync_app(tmp_path):
    db_path = str(tmp_path / "test_ws.db")
    settings.db_path = db_path
    import asyncio

    asyncio.run(init_db(db_path))
    app = create_app(db_path=db_path)
    client = TestClient(app)
    yield client
    if os.path.exists(db_path):
        os.remove(db_path)


def test_websocket_stream_on_incoming_webhook(sync_app):
    channel = "live_test_chan"

    with sync_app.websocket_connect(f"/ws/{channel}") as websocket:
        # Handshake
        initial = websocket.receive_json()
        assert initial["event"] == "connected"
        assert initial["channel_id"] == channel

        # Send an incoming webhook to the catch endpoint
        post_resp = sync_app.post(
            f"/catch/{channel}",
            json={"invoice": "inv_123", "paid": True},
            headers={"X-Custom-Token": "secret99"},
        )
        assert post_resp.status_code == 200

        # WebSocket should receive the real-time event
        event_data = websocket.receive_json()
        assert event_data["event"] == "new_request"
        assert event_data["data"]["channel_id"] == channel
        assert event_data["data"]["body"]["invoice"] == "inv_123"
        assert event_data["data"]["headers"]["x-custom-token"] == "secret99"
