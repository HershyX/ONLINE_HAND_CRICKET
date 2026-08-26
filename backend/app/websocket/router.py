"""
WebSocket route definition.

URL pattern: /ws/rooms/{room_code}?player_id=...&display_name=...
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket

from app.websocket.handler import handle_connection

router = APIRouter(tags=["websocket"])


@router.websocket("/rooms/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    player_id: str = Query(default=""),
    display_name: str = Query(default="Player"),
) -> None:
    """
    Primary WebSocket endpoint.

    The client connects here after creating or joining a room via REST.
    Query params:
      player_id    — the player's UUID (from the REST create/join response)
      display_name — human-readable name (used for reconnect path where REST
                     was skipped)
    """
    await handle_connection(
        websocket=websocket,
        room_code=room_code.upper(),
        player_id=player_id,
        display_name=display_name,
    )
