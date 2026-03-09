from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Set

from fastapi import WebSocket


@dataclass(frozen=True)
class ChannelKey:
    channel_type: str  # "workspace" | "dashboard"
    channel_id: uuid.UUID


class RealtimeManager:
    """In-memory websocket connection manager.

    Note: For true horizontal scaling, replace with Redis pub/sub or a dedicated WS broker.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._channels: Dict[ChannelKey, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            for key in list(self._channels.keys()):
                if websocket in self._channels[key]:
                    self._channels[key].remove(websocket)
                if not self._channels[key]:
                    self._channels.pop(key, None)

    async def subscribe(self, websocket: WebSocket, *, channel_type: str, channel_id: uuid.UUID) -> None:
        key = ChannelKey(channel_type=channel_type, channel_id=channel_id)
        async with self._lock:
            self._channels.setdefault(key, set()).add(websocket)

    async def publish(self, *, channel_type: str, channel_id: uuid.UUID, message: Dict[str, Any]) -> None:
        key = ChannelKey(channel_type=channel_type, channel_id=channel_id)
        async with self._lock:
            recipients = list(self._channels.get(key, set()))
        if not recipients:
            return

        payload = json.dumps(message, separators=(",", ":"), default=str)
        for ws in recipients:
            try:
                await ws.send_text(payload)
            except Exception:
                # Drop on send failure
                await self.disconnect(ws)


REALTIME_MANAGER = RealtimeManager()
