from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.core.security import decode_token
from src.realtime.manager import REALTIME_MANAGER

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket(
    "/realtime",
    name="realtime_websocket",
)
async def realtime_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """WebSocket endpoint for realtime updates.

    Usage:
      - Connect to: /ws/realtime?token=<JWT>
      - Send JSON message: {"action":"subscribe","channel_type":"workspace","channel_id":"<uuid>"}
      - Server sends events as JSON strings.

    Security:
      - Token is validated.
      - Cross-tenant checks happen by requiring org_id claim and comparing subscriptions client-side.
        (For stronger enforcement, couple this with server-side checks against DB for channel_id ownership.)
    """
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        org_id = payload.get("org_id")
        if not sub or not org_id:
            await websocket.close(code=4401)
            return
        # validate UUIDs
        uuid.UUID(str(sub))
        uuid.UUID(str(org_id))
    except Exception:
        await websocket.close(code=4401)
        return

    await REALTIME_MANAGER.connect(websocket)

    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action != "subscribe":
                await websocket.send_json({"type": "error", "detail": "Unsupported action"})
                continue

            channel_type = str(msg.get("channel_type") or "").strip().lower()
            channel_id_raw = msg.get("channel_id")
            if channel_type not in {"workspace", "dashboard"}:
                await websocket.send_json({"type": "error", "detail": "Invalid channel_type"})
                continue
            try:
                channel_id = uuid.UUID(str(channel_id_raw))
            except Exception:
                await websocket.send_json({"type": "error", "detail": "Invalid channel_id"})
                continue

            await REALTIME_MANAGER.subscribe(websocket, channel_type=channel_type, channel_id=channel_id)
            await websocket.send_json({"type": "subscribed", "channel_type": channel_type, "channel_id": str(channel_id)})
    except WebSocketDisconnect:
        await REALTIME_MANAGER.disconnect(websocket)
    except Exception:
        await REALTIME_MANAGER.disconnect(websocket)
        await websocket.close(code=1011)
