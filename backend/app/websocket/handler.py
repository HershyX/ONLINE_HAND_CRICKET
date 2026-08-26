"""
WebSocket message handler.

Transport + dispatch only — no game logic lives here.
Every game decision goes through room_service → engine.

Broadcast policy
────────────────
After every successful action that mutates the game, we broadcast TWO things:

  1. broadcast_game_state(room, event)
       Carries the full authoritative GameState including state_version.
       All clients apply this and update their game view.

  2. broadcast_room_state(room)
       Carries the full Room including updated Player objects (batting/bowling
       stats).  This keeps the live scoreboard accurate after every ball.

On initial connect / reconnect we broadcast ROOM_STATE first (which embeds
the game too), then a separate GAME_STATE so the frontend can update the game
panel immediately with the correct state_version.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket
from pydantic import ValidationError

from app.models.domain import (
    ChatMessagePayload,
    ChooseNumberPayload,
    RequestBatsmanSwitchPayload,
    RequestBowlerSwitchPayload,
    RespondBatsmanSwitchPayload,
    RespondBowlerSwitchPayload,
    Room,
    SetReadyPayload,
    SwitchTeamPayload,
    TossCallPayload,
    TossDecisionPayload,
    TossResponsePayload,
    TransferHostPayload,
    UpdateNamePayload,
    VoteExtraWicketPayload,
    WSMessageType,
)
from app.services import room_service
from app.services.room_service import (
    GameAlreadyStartedError,
    GameError,
    RoomNotFoundError,
)
from app.websocket.connection_manager import manager

logger = logging.getLogger(__name__)


# ─── Connection lifecycle ─────────────────────────────────────────────────────


async def handle_connection(
    websocket: WebSocket,
    room_code: str,
    player_id: str,
    display_name: str,
) -> None:
    await websocket.accept()

    try:
        room, actual_player_id = await room_service.join_room(
            room_code=room_code,
            display_name=display_name,
            player_id=player_id if _looks_like_uuid(player_id) else None,
        )
    except RoomNotFoundError as exc:
        await _send_error(websocket, "ROOM_NOT_FOUND", str(exc))
        await websocket.close(code=4004)
        return
    except GameAlreadyStartedError as exc:
        await _send_error(websocket, "GAME_STARTED", str(exc))
        await websocket.close(code=4003)
        return
    except Exception as exc:
        await _send_error(websocket, "JOIN_FAILED", str(exc))
        await websocket.close(code=4000)
        return

    manager.connect(room_code, actual_player_id, websocket)

    # ── Full reconnection snapshot ────────────────────────────────────────────
    # ROOM_STATE carries the entire room (players, teams, game embedded).
    # The separate GAME_STATE immediately after lets the frontend apply the
    # latest state_version to its dedup filter in a single step.
    await manager.broadcast_room_state(room)
    if room.game is not None:
        await manager.broadcast_game_state(room, WSMessageType.GAME_STATE)

    try:
        while True:
            raw = await websocket.receive_text()
            await _dispatch(websocket, room_code, actual_player_id, raw)
    except Exception:
        pass
    finally:
        manager.disconnect(room_code, actual_player_id)
        try:
            updated = await room_service.player_disconnected(room_code, actual_player_id)
            await manager.broadcast_room_state(updated)
        except Exception:
            pass


# ─── Message dispatcher ───────────────────────────────────────────────────────


async def _dispatch(
    websocket: WebSocket,
    room_code: str,
    player_id: str,
    raw: str,
) -> None:
    try:
        data: dict[str, Any] = json.loads(raw)
        msg_type = WSMessageType(data.get("type", ""))
        payload: dict[str, Any] = data.get("payload", {})
    except (json.JSONDecodeError, ValueError):
        await _send_error(websocket, "INVALID_MESSAGE", "Malformed message")
        return

    try:
        # ── Keep-alive ────────────────────────────────────────────────────────
        if msg_type == WSMessageType.PONG:
            return

        # ── Lobby ─────────────────────────────────────────────────────────────
        elif msg_type == WSMessageType.UPDATE_NAME:
            body = UpdateNamePayload(**payload)
            room = await room_service.update_display_name(
                room_code, player_id, body.display_name
            )
            await manager.broadcast_room_state(room)

        elif msg_type == WSMessageType.SWITCH_TEAM:
            body = SwitchTeamPayload(**payload)
            room = await room_service.switch_team(room_code, player_id, body.team_id)
            await manager.broadcast_room_state(room)

        elif msg_type == WSMessageType.SET_READY:
            body = SetReadyPayload(**payload)
            room = await room_service.set_player_ready(room_code, player_id, body.ready)
            await manager.broadcast_room_state(room)

        elif msg_type == WSMessageType.START_MATCH:
            room = await room_service.start_match(room_code, player_id)
            await manager.broadcast_room_state(room)
            if room.game:
                await manager.broadcast_game_state(room, WSMessageType.GAME_STARTED)

        # ── Host transfer ──────────────────────────────────────────────────────
        elif msg_type == WSMessageType.TRANSFER_HOST:
            body = TransferHostPayload(**payload)
            room = await room_service.transfer_host(room_code, player_id, body.new_host_id)
            await manager.broadcast_room_state(room)

        # ── Return to lobby after game ─────────────────────────────────────────
        elif msg_type == WSMessageType.RETURN_TO_LOBBY:
            room, _ = await room_service.return_to_lobby(room_code, player_id)
            # Broadcast to ALL so they see the updated ready state,
            # but each client navigates independently based on their own UI.
            await manager.broadcast_room_state(room)

        # ── Chat ───────────────────────────────────────────────────────────────
        elif msg_type == WSMessageType.CHAT_MESSAGE:
            body = ChatMessagePayload(**payload)
            room, msg = await room_service.add_chat_message(
                room_code, player_id, body.scope, body.content
            )
            chat_payload = msg.model_dump(mode="json")
            if body.scope == "global":
                await manager.broadcast(room_code, WSMessageType.CHAT_MESSAGE, chat_payload)
            else:
                # Team chat — only send to the sender's team
                sender = room.players.get(player_id)
                if sender and sender.team_id:
                    await manager.broadcast_to_team(
                        room, sender.team_id, WSMessageType.CHAT_MESSAGE, chat_payload
                    )

        # ── Toss ──────────────────────────────────────────────────────────────
        elif msg_type == WSMessageType.TOSS_CALL:
            body   = TossCallPayload(**payload)
            number = int(payload.get("number", 0))
            result = await room_service.submit_toss_call(
                room_code, player_id, body.call, number
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        elif msg_type == WSMessageType.TOSS_RESPONSE:
            body   = TossResponsePayload(**payload)
            result = await room_service.submit_toss_response(
                room_code, player_id, body.number
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        elif msg_type == WSMessageType.TOSS_DECISION:
            body   = TossDecisionPayload(**payload)
            result = await room_service.submit_toss_decision(
                room_code, player_id, body.decision
            )
            if room := await _get_room(room_code):
                # Also send ROOM_STATE so all clients get the team/player context
                # needed to render the toss_announcement banner correctly.
                await manager.broadcast_room_state(room)
                await manager.broadcast_game_state(room, result.event)

        # ── Ball play ─────────────────────────────────────────────────────────
        elif msg_type == WSMessageType.CHOOSE_NUMBER:
            body   = ChooseNumberPayload(**payload)
            result = await room_service.submit_number(room_code, player_id, body.number)
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)
                await manager.broadcast_room_state(room)
                await _try_persist_match(room)

        # ── Extra-wicket voting ───────────────────────────────────────────────
        elif msg_type == WSMessageType.VOTE_EXTRA_WICKET:
            body   = VoteExtraWicketPayload(**payload)
            result = await room_service.vote_extra_wicket(
                room_code, player_id, body.candidate_player_id
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)
                await _try_persist_match(room)

        # ── Bowler switching ──────────────────────────────────────────────────
        elif msg_type == WSMessageType.REQUEST_BOWLER_SWITCH:
            body   = RequestBowlerSwitchPayload(**payload)
            result = await room_service.request_bowler_switch(
                room_code, player_id, body.incoming_bowler_id
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        elif msg_type == WSMessageType.RESPOND_BOWLER_SWITCH:
            body   = RespondBowlerSwitchPayload(**payload)
            result = await room_service.respond_bowler_switch(
                room_code, player_id, body.accept
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        # ── Batsman switching ─────────────────────────────────────────────────
        elif msg_type == WSMessageType.REQUEST_BATSMAN_SWITCH:
            result = await room_service.request_batsman_switch(room_code, player_id)
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        elif msg_type == WSMessageType.RESPOND_BATSMAN_SWITCH:
            body   = RespondBatsmanSwitchPayload(**payload)
            result = await room_service.respond_batsman_switch(
                room_code, player_id, body.accept, body.chosen_player_id
            )
            if room := await _get_room(room_code):
                await manager.broadcast_game_state(room, result.event)

        # ── Innings transition ────────────────────────────────────────────────
        elif msg_type == WSMessageType.START_SECOND_INNINGS:
            result = await room_service.start_second_innings(room_code, player_id)
            if room := await _get_room(room_code):
                await manager.broadcast_room_state(room)
                await manager.broadcast_game_state(room, result.event)

        else:
            await _send_error(
                websocket, "UNKNOWN_MESSAGE", f"Unknown message type: {msg_type}"
            )

    except (ValidationError, ValueError) as exc:
        await _send_error(websocket, "VALIDATION_ERROR", str(exc))
    except GameAlreadyStartedError as exc:
        await _send_error(websocket, "GAME_STARTED", str(exc))
    except GameError as exc:
        await _send_error(websocket, "GAME_ERROR", str(exc))
    except RoomNotFoundError as exc:
        await _send_error(websocket, "ROOM_NOT_FOUND", str(exc))
    except Exception as exc:
        logger.exception("Unhandled WS error for player %s: %s", player_id, exc)
        await _send_error(websocket, "INTERNAL_ERROR", "An unexpected error occurred")


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    from datetime import datetime, timezone
    try:
        await websocket.send_json({
            "type": WSMessageType.ERROR.value,
            "payload": {"code": code, "message": message},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


async def _get_room(room_code: str) -> Room | None:
    from app.game.state import registry
    return await registry.get(room_code)


async def _try_persist_match(room: Room) -> None:
    """Persist the match to the database if it just ended."""
    game = room.game
    if game is None or game.status.value != "GAME_OVER" or game.final_result is None:
        return

    from app.db import persist_match

    result = game.final_result
    inn1 = game.innings_history[0] if len(game.innings_history) > 0 else None
    inn2 = game.innings_history[1] if len(game.innings_history) > 1 else None

    margin: str | None = None
    if result.margin_runs is not None:
        margin = f"{result.margin_runs} runs"
    elif result.margin_wickets is not None:
        margin = f"{result.margin_wickets} wickets"

    mvp_name: str | None = None
    if result.mvp_player_id:
        mvp_player = room.players.get(result.mvp_player_id)
        if mvp_player:
            mvp_name = mvp_player.display_name

    team_a = room.teams.get("team_a")
    team_b = room.teams.get("team_b")

    await persist_match(
        room_code=room.room_code,
        team_a_name=team_a.name if team_a else "Team A",
        team_b_name=team_b.name if team_b else "Team B",
        team_a_score=inn1.score if inn1 and inn1.batting_team_id == "team_a" else (inn2.score if inn2 and inn2.batting_team_id == "team_a" else 0),
        team_a_wickets=inn1.wickets if inn1 and inn1.batting_team_id == "team_a" else (inn2.wickets if inn2 and inn2.batting_team_id == "team_a" else 0),
        team_a_balls=len(inn1.balls) if inn1 and inn1.batting_team_id == "team_a" else (len(inn2.balls) if inn2 and inn2.batting_team_id == "team_a" else 0),
        team_b_score=inn1.score if inn1 and inn1.batting_team_id == "team_b" else (inn2.score if inn2 and inn2.batting_team_id == "team_b" else 0),
        team_b_wickets=inn1.wickets if inn1 and inn1.batting_team_id == "team_b" else (inn2.wickets if inn2 and inn2.batting_team_id == "team_b" else 0),
        team_b_balls=len(inn1.balls) if inn1 and inn1.batting_team_id == "team_b" else (len(inn2.balls) if inn2 and inn2.batting_team_id == "team_b" else 0),
        winner_team_id=result.winner_team_id,
        is_tie=result.is_tie,
        margin=margin,
        mvp_player_id=result.mvp_player_id,
        mvp_player_name=mvp_name,
        player_count=len(room.players),
    )


def _looks_like_uuid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4
