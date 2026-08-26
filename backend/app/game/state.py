"""
In-memory room registry.

All active Room objects live here. The design is intentionally simple:
  - A plain dict guarded by an asyncio.Lock.
  - The lock is per-room to allow concurrent operations on different rooms.
  - Easy to swap for Redis later by replacing RoomRegistry with a Redis-backed
    implementation behind the same interface.

No game logic lives here — just storage and lookup.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.models.domain import Room


class RoomRegistry:
    """Thread-safe in-memory store for active Room objects."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def create(self, room: Room) -> Room:
        async with self._global_lock:
            self._rooms[room.room_code] = room
            self._locks[room.room_code] = asyncio.Lock()
        return room

    async def get(self, room_code: str) -> Optional[Room]:
        return self._rooms.get(room_code)

    async def get_lock(self, room_code: str) -> Optional[asyncio.Lock]:
        return self._locks.get(room_code)

    async def delete(self, room_code: str) -> None:
        async with self._global_lock:
            self._rooms.pop(room_code, None)
            self._locks.pop(room_code, None)

    async def list_codes(self) -> list[str]:
        return list(self._rooms.keys())

    def __len__(self) -> int:
        return len(self._rooms)


# Module-level singleton
registry = RoomRegistry()
