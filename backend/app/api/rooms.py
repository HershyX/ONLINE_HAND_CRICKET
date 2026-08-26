"""
REST API routes for room management.

These routes handle pre-WebSocket operations:
  POST /api/rooms        — create a room
  GET  /api/rooms/{code} — look up a room (for join validation)
  GET  /api/health       — already on the root app, but a duplicate here is fine

All mutating game operations happen over WebSocket.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.game.state import registry
from app.services.room_service import (
    RoomFullError,
    RoomNotFoundError,
    create_room,
)

router = APIRouter(tags=["rooms"])


# ─── Request / Response models ────────────────────────────────────────────────


class CreateRoomRequest(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=20)
    # 0 = unlimited overs (game ends on wicket only); 1-50 = fixed overs
    overs_per_innings: int = Field(
        default=0,
        ge=0,
        le=settings.max_overs_per_innings,
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, v: str) -> str:
        # Strip before validating so the length check matches the Player
        # model's validator — otherwise a name like " A " passes here but
        # raises inside create_room, producing an unhandled 500.
        v = v.strip()
        if len(v) < 2 or len(v) > 20:
            raise ValueError("Display name must be 2–20 characters")
        return v


class CreateRoomResponse(BaseModel):
    room_code: str
    host_player_id: str


class RoomInfoResponse(BaseModel):
    room_code: str
    player_count: int
    max_players: int
    room_status: str


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/rooms",
    response_model=CreateRoomResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_room_endpoint(body: CreateRoomRequest) -> CreateRoomResponse:
    """Create a new private room. Returns the room code and host player id."""
    room, host_id = await create_room(
        display_name=body.display_name,
        overs_per_innings=body.overs_per_innings,
    )
    return CreateRoomResponse(room_code=room.room_code, host_player_id=host_id)


@router.get("/rooms/{room_code}", response_model=RoomInfoResponse)
async def get_room_info(room_code: str) -> RoomInfoResponse:
    """
    Fetch basic metadata about a room.
    Used by the frontend to validate a room exists before opening a WebSocket.
    """
    room = await registry.get(room_code.upper())
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_code}' not found",
        )
    return RoomInfoResponse(
        room_code=room.room_code,
        player_count=len(room.connected_players()),
        max_players=room.max_players,
        room_status=room.room_status.value,
    )
