import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("hook_trap.ws")


class ConnectionManager:
    """Manages WebSocket connections and channel subscriptions."""

    def __init__(self) -> None:
        # Map channel_id -> set of active WebSockets
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel_id: str, websocket: WebSocket) -> None:
        """Accept connection and register with channel."""
        await websocket.accept()
        async with self._lock:
            if channel_id not in self._connections:
                self._connections[channel_id] = set()
            self._connections[channel_id].add(websocket)
        logger.debug("Client connected to channel %s", channel_id)

    async def disconnect(self, channel_id: str, websocket: WebSocket) -> None:
        """Unregister connection and clean up empty channel buckets."""
        async with self._lock:
            if channel_id in self._connections:
                self._connections[channel_id].discard(websocket)
                if not self._connections[channel_id]:
                    del self._connections[channel_id]
        logger.debug("Client disconnected from channel %s", channel_id)

    async def broadcast(self, channel_id: str, message: dict[str, Any]) -> None:
        """Broadcast a JSON message to all clients connected to channel_id."""
        async with self._lock:
            sockets = list(self._connections.get(channel_id, []))

        if not sockets:
            return

        payload = json.dumps(message)
        dead_sockets: list[WebSocket] = []

        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.debug("Failed sending to socket: %s", exc)
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                if channel_id in self._connections:
                    for dead in dead_sockets:
                        self._connections[channel_id].discard(dead)
                    if not self._connections[channel_id]:
                        del self._connections[channel_id]

    def get_subscriber_count(self, channel_id: str) -> int:
        """Get number of active subscribers for a channel."""
        return len(self._connections.get(channel_id, []))


# Global singleton instance
ws_manager = ConnectionManager()
