from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.schemas.realtime import LiveEventType
from app.services.realtime import build_live_event, live_connections


router = APIRouter(prefix="/matches", tags=["realtime"])


@router.websocket("/{match_id}/live")
async def match_live_websocket(match_id: UUID, websocket: WebSocket) -> None:
    await live_connections.connect(match_id, websocket)

    try:
        event = await build_live_event(match_id, LiveEventType.SNAPSHOT)
        await websocket.send_json(event.model_dump(mode="json"))

        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        pass


    finally:
        await live_connections.disconnect(match_id, websocket)

