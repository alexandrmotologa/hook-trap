import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hook_trap.ws_manager import ws_manager

logger = logging.getLogger("hook_trap.ws")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/{channel_id}")
async def channel_websocket(websocket: WebSocket, channel_id: str) -> None:
    """Live stream connection for a channel."""
    await ws_manager.connect(channel_id, websocket)
    try:
        # Initial greeting
        await websocket.send_text(
            json.dumps({"event": "connected", "channel_id": channel_id})
        )

        while True:
            # Wait for client messages or keepalive pings with timeout
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=35.0)
                # Client ping response
                if data == "ping":
                    await websocket.send_text("pong")
            except TimeoutError:
                # Server-initiated heartbeat ping
                await websocket.send_text(json.dumps({"event": "ping"}))
    except WebSocketDisconnect:
        await ws_manager.disconnect(channel_id, websocket)
    except Exception as exc:
        logger.debug("WebSocket error on channel %s: %s", channel_id, exc)
        await ws_manager.disconnect(channel_id, websocket)
