"""
WebSocket connection manager.

Tracks all live connections grouped by room code.
Provides broadcast helpers used by the message handler.

Deliberately simple — no Redis pub/sub, no external dependencies.
Swappable for a distributed implementation behind the same interface.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.models.domain import Room, WSMessageType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages live WebSocket connections across all rooms."""

    def __init__(self) -> None:
        # room_code → {player_id: WebSocket}
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self, room_code: str, player_id: str, ws: WebSocket) -> None:
        if room_code not in self._rooms:
            self._rooms[room_code] = {}
        self._rooms[room_code][player_id] = ws
        logger.info("WS connected: room=%s player=%s", room_code, player_id)

    def disconnect(self, room_code: str, player_id: str) -> None:
        room_conns = self._rooms.get(room_code, {})
        room_conns.pop(player_id, None)
        if not room_conns:
            self._rooms.pop(room_code, None)
        logger.info("WS disconnected: room=%s player=%s", room_code, player_id)

    def is_connected(self, room_code: str, player_id: str) -> bool:
        ws = self._rooms.get(room_code, {}).get(player_id)
        return ws is not None and ws.client_state == WebSocketState.CONNECTED

    def player_count(self, room_code: str) -> int:
        return len(self._rooms.get(room_code, {}))

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send_to(
        self,
        room_code: str,
        player_id: str,
        message_type: WSMessageType,
        payload: dict[str, Any],
    ) -> None:
        ws = self._rooms.get(room_code, {}).get(player_id)
        if ws is None:
            return
        await self._send(ws, message_type, payload)

    async def broadcast(
        self,
        room_code: str,
        message_type: WSMessageType,
        payload: dict[str, Any],
        exclude_player: Optional[str] = None,
    ) -> None:
        """Send a message to all connected players in a room."""
        conns = dict(self._rooms.get(room_code, {}))  # copy to avoid mutation
        tasks = []
        for pid, ws in conns.items():
            if pid == exclude_player:
                continue
            tasks.append(self._send(ws, message_type, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_room_state(self, room: Room) -> None:
        """
        Broadcast the full room snapshot to every connected player.
        Each player receives their own player_id in the envelope.
        """
        conns = dict(self._rooms.get(room.room_code, {}))
        tasks = []
        for pid, ws in conns.items():
            payload = {
                "room": room.model_dump(mode="json"),
                "your_player_id": pid,
            }
            tasks.append(self._send(ws, WSMessageType.ROOM_STATE, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_game_state(
        self,
        room: Room,
        event: WSMessageType = WSMessageType.GAME_STATE,
    ) -> None:
        """Broadcast the current game state to all players in the room."""
        if room.game is None:
            return
        payload = room.game.model_dump(mode="json")
        await self.broadcast(room.room_code, event, payload)

    async def broadcast_to_team(
        self,
        room: Room,
        team_id: str,
        message_type: WSMessageType,
        payload: dict[str, Any],
    ) -> None:
        """Send a message only to players on a specific team."""
        conns = dict(self._rooms.get(room.room_code, {}))
        tasks = []
        for pid, ws in conns.items():
            player = room.players.get(pid)
            if player and player.team_id == team_id:
                tasks.append(self._send(ws, message_type, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    async def _send(
        ws: WebSocket,
        message_type: WSMessageType,
        payload: dict[str, Any],
    ) -> None:
        if ws.client_state != WebSocketState.CONNECTED:
            return
        try:
            envelope = {
                "type": message_type.value,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await ws.send_json(envelope)
        except Exception as exc:
            logger.warning("Failed to send WS message: %s", exc)


# Module-level singleton
manager = ConnectionManager()
