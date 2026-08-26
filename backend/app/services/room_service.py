"""
Room service — orchestrates room lifecycle using the registry and engine.

All methods are async and acquire per-room locks before mutating state.
The WebSocket handler calls these; it never touches the engine directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.game.engine import EngineResult, engine
from app.game.state import registry
from app.models.domain import (
    GameState,
    GameStatus,
    Player,
    Room,
    RoomStatus,
    StartMatchValidation,
    Team,
    TossCall,
    TossDecision,
    compute_extra_wicket,
    validate_team_sizes,
)


# ─── Typed errors ─────────────────────────────────────────────────────────────


class RoomNotFoundError(Exception):
    pass


class RoomFullError(Exception):
    pass


class GameAlreadyStartedError(Exception):
    pass


class GameError(Exception):
    pass


# ─── Room lifecycle ───────────────────────────────────────────────────────────


async def create_room(
    display_name: str,
    overs_per_innings: int = 0,  # kept for API compat; engine ignores it
) -> tuple[Room, str]:
    host_id = str(uuid.uuid4())
    player  = Player(id=host_id, display_name=display_name)
    player.team_id = "team_a"

    team_a = Team(id="team_a", name="Team 1", player_ids=[host_id])
    team_b = Team(id="team_b", name="Team 2")

    room = Room(host_id=host_id)
    room.players[host_id] = player
    room.teams["team_a"]  = team_a
    room.teams["team_b"]  = team_b
    room.game             = GameState()

    await registry.create(room)
    return room, host_id


async def join_room(
    room_code: str,
    display_name: str,
    player_id: Optional[str] = None,
) -> tuple[Room, str]:
    room = await registry.get(room_code)
    if room is None:
        raise RoomNotFoundError(f"Room '{room_code}' not found")

    lock = await registry.get_lock(room_code)
    assert lock is not None

    async with lock:
        # Reconnect path
        if player_id and player_id in room.players:
            room.players[player_id].connected = True
            if room.room_status == RoomStatus.WAITING:
                room.players[player_id].ready = False
            return room, player_id

        # New join guards — block only while a match is actively in play
        if room.room_status == RoomStatus.IN_GAME:
            raise GameAlreadyStartedError("The game has already started")
        if len(room.connected_players()) >= room.max_players:
            raise RoomFullError("Room is full")

        # Assign to the smaller team
        a_count, b_count = room.team_counts()
        team_id = "team_a" if a_count <= b_count else "team_b"

        pid    = str(uuid.uuid4())
        player = Player(id=pid, display_name=display_name)
        player.team_id = team_id
        room.teams[team_id].player_ids.append(pid)
        room.players[pid] = player

        _refresh_room_status(room)
        return room, pid


async def player_disconnected(room_code: str, player_id: str) -> Room:
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        player = room.get_player(player_id)
        if player:
            player.connected = False
            if room.room_status == RoomStatus.WAITING:
                player.ready = False
        _refresh_room_status(room)
        return room


# ─── Lobby actions ────────────────────────────────────────────────────────────


async def update_display_name(
    room_code: str, player_id: str, new_name: str
) -> Room:
    new_name = new_name.strip()
    if len(new_name) < 2 or len(new_name) > 20:
        raise GameError("Display name must be 2–20 characters")
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        if room.room_status == RoomStatus.IN_GAME:
            raise GameError("Cannot change name during an active game")
        player = room.get_player(player_id)
        if player is None:
            raise GameError("Player not found")
        player.display_name = new_name
        return room


async def switch_team(
    room_code: str, player_id: str, target_team_id: str
) -> Room:
    if target_team_id not in ("team_a", "team_b"):
        raise GameError("Invalid team id")
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        if room.room_status == RoomStatus.IN_GAME:
            raise GameError("Team membership is locked once the game starts")
        player = room.get_player(player_id)
        if player is None:
            raise GameError("Player not found")
        if player.team_id == target_team_id:
            return room
        if player.team_id and player.team_id in room.teams:
            old = room.teams[player.team_id]
            if player_id in old.player_ids:
                old.player_ids.remove(player_id)
        room.teams[target_team_id].player_ids.append(player_id)
        player.team_id = target_team_id
        player.ready   = False
        _refresh_room_status(room)
        return room


async def set_player_ready(
    room_code: str, player_id: str, ready: bool
) -> Room:
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        if room.room_status == RoomStatus.IN_GAME:
            raise GameError("Game is already in progress")
        player = room.get_player(player_id)
        if player is None:
            raise GameError("Player not found")
        player.ready = ready
        _refresh_room_status(room)
        return room


async def start_match(room_code: str, requesting_player_id: str) -> Room:
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        v = _can_start_match(room, requesting_player_id)
        if not v.can_start:
            raise GameError("; ".join(v.reasons))

        # ── Reset game state for a new match ──────────────────────────────────
        # This handles both first games and rematches after RETURN_TO_LOBBY.
        # We always create a fresh GameState so toss metadata from previous
        # games never leaks into the new one.
        from app.models.domain import BattingStats, BowlingStats
        for p in room.players.values():
            p.batting_stats = BattingStats()
            p.bowling_stats = BowlingStats()
            # NOTE: do NOT reset p.ready here — the engine's start_toss()
            # requires all connected players to be ready, and validation has
            # already passed. Players re-ready via the lobby between games.

        for team in room.teams.values():
            team.score = 0
            team.wickets = 0
            team.extra_wicket_available = False

        room.game = GameState()

        a_count, b_count    = room.team_counts()
        extra_a, extra_b    = compute_extra_wicket(a_count, b_count)
        room.teams["team_a"].extra_wicket_available = extra_a
        room.teams["team_b"].extra_wicket_available = extra_b

        room.room_status = RoomStatus.IN_GAME
        result = engine.start_toss(room)
        if not result.success:
            room.room_status = RoomStatus.WAITING
            raise GameError(result.error or "Failed to start toss")
        return room


def can_start_match_public(
    room: Room, requesting_player_id: str
) -> StartMatchValidation:
    return _can_start_match(room, requesting_player_id)


# ─── Return to lobby after game ──────────────────────────────────────────────


async def return_to_lobby(room_code: str, player_id: str) -> tuple[Room, str]:
    """
    A single player chooses to go back to the lobby after a game ends.

    This is PERSONAL — it only affects the requesting player:
      - Marks them not-ready.
      - Does NOT reset the game, other players' stats, or room_status.
      - Returns (room, player_id) so the handler can send a targeted
        ROOM_STATE only to this player (via their existing WS connection).

    The room is broadcast to everyone so they see who has "returned" (via
    ready=False), but nobody else is force-navigated anywhere.

    The actual game reset (new GameState, cleared stats) happens lazily
    inside start_match when the host kicks off the next game.
    """
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        player = room.get_player(player_id)
        if player is None:
            raise GameError("Player not found")
        # Mark this player as not-ready (they're in the lobby now)
        player.ready = False
        return room, player_id


# ─── Host transfer ────────────────────────────────────────────────────────────


async def transfer_host(    room_code: str, requesting_player_id: str, new_host_id: str
) -> Room:
    """
    Transfer host privileges from the current host to another connected player.
    Only the current host may call this.
    """
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        if room.host_id != requesting_player_id:
            raise GameError("Only the current host can transfer host privileges")
        if new_host_id not in room.players:
            raise GameError("Target player not found in this room")
        if not room.players[new_host_id].connected:
            raise GameError("Cannot transfer host to a disconnected player")
        if new_host_id == requesting_player_id:
            raise GameError("You are already the host")
        room.host_id = new_host_id
        return room


# ─── Chat ─────────────────────────────────────────────────────────────────────


async def add_chat_message(
    room_code: str,
    player_id: str,
    scope: str,
    content: str,
) -> tuple[Room, "ChatMessage"]:
    """
    Add a chat message to the room's chat history.
    scope: "global" (all players) or "team" (same team only).
    """
    import uuid as _uuid
    from app.models.domain import ChatMessage

    if scope not in ("global", "team"):
        raise GameError("Invalid chat scope — must be 'global' or 'team'")

    content = content.strip()
    if not content:
        raise GameError("Message cannot be empty")
    if len(content) > 200:
        raise GameError("Message too long (max 200 chars)")

    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None

    async with lock:
        player = room.get_player(player_id)
        if player is None:
            raise GameError("Player not found")

        msg = ChatMessage(
            id=str(_uuid.uuid4()),
            player_id=player_id,
            display_name=player.display_name,
            team_id=player.team_id,
            scope=scope,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        room.chat_messages.append(msg)
        # Cap history at 100 messages to prevent unbounded memory growth
        if len(room.chat_messages) > 100:
            room.chat_messages = room.chat_messages[-100:]
        return room, msg


# ─── Toss actions ─────────────────────────────────────────────────────────────


async def submit_toss_call(
    room_code: str, player_id: str, call: TossCall, number: int
) -> EngineResult:
    return await _engine_action(
        room_code, lambda r: engine.submit_toss_call(r, player_id, call, number)
    )


async def submit_toss_response(
    room_code: str, player_id: str, number: int
) -> EngineResult:
    return await _engine_action(
        room_code, lambda r: engine.submit_toss_response(r, player_id, number)
    )


async def submit_toss_decision(
    room_code: str, player_id: str, decision: TossDecision
) -> EngineResult:
    return await _engine_action(
        room_code, lambda r: engine.submit_toss_decision(r, player_id, decision)
    )


# ─── Ball-play actions ────────────────────────────────────────────────────────


async def submit_number(
    room_code: str, player_id: str, number: int
) -> EngineResult:
    return await _engine_action(
        room_code, lambda r: engine.submit_number(r, player_id, number)
    )


# ─── Extra-wicket voting ──────────────────────────────────────────────────────


async def vote_extra_wicket(
    room_code: str, player_id: str, candidate_player_id: str
) -> EngineResult:
    return await _engine_action(
        room_code,
        lambda r: engine.submit_extra_wicket_vote(r, player_id, candidate_player_id),
    )


# ─── Bowler switching ─────────────────────────────────────────────────────────


async def request_bowler_switch(
    room_code: str, player_id: str, incoming_bowler_id: str
) -> EngineResult:
    return await _engine_action(
        room_code,
        lambda r: engine.request_bowler_switch(r, player_id, incoming_bowler_id),
    )


async def respond_bowler_switch(
    room_code: str, player_id: str, accept: bool
) -> EngineResult:
    return await _engine_action(
        room_code,
        lambda r: engine.respond_bowler_switch(r, player_id, accept),
    )


# ─── Innings transition ───────────────────────────────────────────────────────


async def start_second_innings(room_code: str, requesting_player_id: str) -> EngineResult:
    """Only the room host may start the second innings."""
    room = await _get_room(room_code)
    if room.host_id != requesting_player_id:
        raise GameError("Only the host can start the second innings")
    return await _engine_action(
        room_code, lambda r: engine.start_second_innings(r)
    )


# ─── Batsman switching ────────────────────────────────────────────────────────


async def request_batsman_switch(
    room_code: str, player_id: str
) -> EngineResult:
    return await _engine_action(
        room_code,
        lambda r: engine.request_batsman_switch(r, player_id),
    )


async def respond_batsman_switch(
    room_code: str, player_id: str, accept: bool, chosen_player_id: str | None = None
) -> EngineResult:
    return await _engine_action(
        room_code,
        lambda r: engine.respond_batsman_switch(r, player_id, accept, chosen_player_id),
    )


# ─── Private helpers ──────────────────────────────────────────────────────────


async def _get_room(room_code: str) -> Room:
    room = await registry.get(room_code)
    if room is None:
        raise RoomNotFoundError(f"Room '{room_code}' not found")
    return room


async def _engine_action(
    room_code: str,
    action,
) -> EngineResult:
    """Acquire the room lock, run `action(room)`, raise on failure."""
    room = await _get_room(room_code)
    lock = await registry.get_lock(room_code)
    assert lock is not None
    async with lock:
        result = action(room)
        if not result.success:
            raise GameError(result.error or "Unknown game error")
        return result


def _refresh_room_status(room: Room) -> None:
    if room.room_status in (RoomStatus.IN_GAME, RoomStatus.FINISHED):
        return
    connected = room.connected_players()
    room.room_status = (
        RoomStatus.READY if len(connected) >= 2 else RoomStatus.WAITING
    )


def _can_start_match(
    room: Room, requesting_player_id: str
) -> StartMatchValidation:
    reasons: list[str] = []

    if room.host_id != requesting_player_id:
        reasons.append("Only the host can start the match")

    connected = room.connected_players()
    if len(connected) < 2:
        reasons.append("Need at least 2 players to start")

    # Allow starting a new game after GAME_OVER (rematch)
    game_in_progress = (
        room.room_status == RoomStatus.IN_GAME
        and room.game is not None
        and room.game.status != GameStatus.GAME_OVER
    )
    if game_in_progress:
        reasons.append("A game is already in progress")

    not_ready = [p for p in connected if not p.ready]
    if not_ready:
        names = ", ".join(p.display_name for p in not_ready)
        reasons.append(f"Not ready: {names}")

    a_count, b_count = room.team_counts()
    team_err = validate_team_sizes(a_count, b_count)
    if team_err:
        reasons.append(team_err)

    return StartMatchValidation(can_start=len(reasons) == 0, reasons=reasons)
