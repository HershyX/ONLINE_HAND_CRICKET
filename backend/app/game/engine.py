"""
Hand Cricket game engine — the sole authoritative state machine.

Responsibilities:
  - Validates every player action against the current game state.
  - Applies domain rules (from rules.py) — never duplicates logic.
  - Mutates GameState / InningsState objects passed in.
  - Returns EngineResult so the caller can broadcast the correct WS event.
  - Never touches I/O — fully testable without FastAPI or WebSockets.

Design invariants:
  - No randomness: toss resolution is arithmetic, not random.
  - No timers: the engine waits indefinitely for players.
  - No automatic moves: every transition requires an explicit player action.
  - The backend is the single source of truth for every game decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.game.rules import (
    calculate_result,
    is_innings_complete,
    is_target_reached,
    resolve_ball,
    resolve_toss,
)
from app.models.domain import (
    BatsmanSwitchState,
    BowlerSwitchState,
    ExtraWicketVoteState,
    FinalResult,
    GameState,
    GameStatus,
    InningsHistory,
    InningsState,
    Room,
    RoomStatus,
    TossCall,
    TossDecision,
    WSMessageType,
    bump_version,
)


# ─── Engine result ────────────────────────────────────────────────────────────


@dataclass
class EngineResult:
    """Returned by every public engine method."""
    success: bool
    event:   WSMessageType
    game:    GameState
    error:   Optional[str] = None


# ─── State-transition table ───────────────────────────────────────────────────

_VALID_TRANSITIONS: dict[GameStatus, set[GameStatus]] = {
    GameStatus.LOBBY:             {GameStatus.TOSS},
    GameStatus.TOSS:              {GameStatus.TOSS_DECISION},
    GameStatus.TOSS_DECISION:     {GameStatus.INNINGS_SETUP},
    GameStatus.INNINGS_SETUP:     {GameStatus.CHOOSING_NUMBERS},
    GameStatus.CHOOSING_NUMBERS:  {GameStatus.RESOLVING_BALL,
                                   GameStatus.BOWLER_SWITCH},
    GameStatus.RESOLVING_BALL:    {GameStatus.CHOOSING_NUMBERS,
                                   GameStatus.PLAYER_OUT,
                                   GameStatus.INNINGS_BREAK,
                                   GameStatus.GAME_OVER},
    GameStatus.PLAYER_OUT:        {GameStatus.CHOOSING_NUMBERS,
                                   GameStatus.EXTRA_WICKET_VOTE,
                                   GameStatus.INNINGS_BREAK,
                                   GameStatus.GAME_OVER},
    GameStatus.EXTRA_WICKET_VOTE: {GameStatus.CHOOSING_NUMBERS,
                                   GameStatus.INNINGS_BREAK,
                                   GameStatus.GAME_OVER},
    GameStatus.BOWLER_SWITCH:     {GameStatus.CHOOSING_NUMBERS},
    GameStatus.INNINGS_BREAK:     {GameStatus.SECOND_INNINGS},
    GameStatus.SECOND_INNINGS:    {GameStatus.CHOOSING_NUMBERS},
    GameStatus.GAME_OVER:         set(),
}


def _transition(game: GameState, new_status: GameStatus) -> None:
    allowed = _VALID_TRANSITIONS.get(game.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {game.status.value} → {new_status.value}"
        )
    game.status = new_status


# ─── Ephemeral metadata (never serialised to clients) ────────────────────────
# Stored in game.__dict__ under these keys so Pydantic doesn't see them.

_KEY_TOSS_META = "_toss_meta"   # dict with caller_id, call, caller_number
_KEY_BALL_META = "_ball_meta"   # dict with "batsman" and/or "bowler" numbers


# ─── Engine ───────────────────────────────────────────────────────────────────


class GameEngine:
    """
    Stateless — all state lives in Room/GameState objects passed in.
    Safe to instantiate once as a module-level singleton.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # LOBBY → TOSS
    # ═══════════════════════════════════════════════════════════════════════════

    def start_toss(self, room: Room) -> EngineResult:
        """
        Called by room_service.start_match() after lobby validation passes.

        Picks one representative from each team to participate in the toss
        (first player in team_ids list for determinism) and transitions to TOSS.
        """
        game = room.game
        if game is None:
            return self._err(None, "No game object on room")

        if game.status != GameStatus.LOBBY:
            return self._err(game, "Game has already started")

        if not room.all_ready():
            return self._err(game, "Not all players are ready")

        # Pick one toss representative per team
        team_a_players = [
            pid for pid in room.teams["team_a"].player_ids
            if pid in room.players and room.players[pid].connected
        ]
        team_b_players = [
            pid for pid in room.teams["team_b"].player_ids
            if pid in room.players and room.players[pid].connected
        ]
        if not team_a_players or not team_b_players:
            return self._err(game, "Each team needs at least one connected player")

        # The team_a representative calls the toss; team_b responds.
        game.toss_caller_player_id   = team_a_players[0]
        game.toss_responder_player_id = team_b_players[0]

        _transition(game, GameStatus.TOSS)
        return self._ok(game, WSMessageType.GAME_STARTED)

    # ═══════════════════════════════════════════════════════════════════════════
    # TOSS — caller submits ODD/EVEN + their number
    # ═══════════════════════════════════════════════════════════════════════════

    def submit_toss_call(
        self,
        room: Room,
        player_id: str,
        call: TossCall,
        number: int,
    ) -> EngineResult:
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.TOSS:
            return self._err(game, f"Toss not in progress (state={game.status.value})")
        if player_id != game.toss_caller_player_id:
            return self._err(game, "You are not the toss caller for this match")
        if not (0 <= number <= 10):
            return self._err(game, "Toss number must be 0–10")

        game.__dict__[_KEY_TOSS_META] = {
            "caller_id": player_id,
            "call": call,
            "caller_number": number,
        }
        # Reveal only the ODD/EVEN call so the responder knows when to submit
        game.toss_call_made = call
        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # TOSS — responder submits their number → toss resolved
    # ═══════════════════════════════════════════════════════════════════════════

    def submit_toss_response(
        self,
        room: Room,
        player_id: str,
        number: int,
    ) -> EngineResult:
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.TOSS:
            return self._err(game, f"Toss not in progress (state={game.status.value})")
        if player_id != game.toss_responder_player_id:
            return self._err(game, "You are not the toss responder for this match")
        if not (0 <= number <= 10):
            return self._err(game, "Toss number must be 0–10")

        meta = game.__dict__.get(_KEY_TOSS_META)
        if not meta:
            return self._err(game, "Toss call has not been submitted yet")

        caller_id: str     = meta["caller_id"]
        call: TossCall     = meta["call"]
        caller_number: int = meta["caller_number"]

        # Determine which team each player belongs to
        caller_team  = room.players[caller_id].team_id   # "team_a" or "team_b"
        responder_team = room.players[player_id].team_id

        winner_player_id = resolve_toss(
            caller_id=caller_id,
            other_id=player_id,
            caller_call=call,
            caller_number=caller_number,
            other_number=number,
        )
        game.toss_winner_team_id = room.players[winner_player_id].team_id

        # ── Reveal both numbers publicly now that the toss is resolved ──────
        game.toss_caller_number    = caller_number
        game.toss_responder_number = number

        game.__dict__.pop(_KEY_TOSS_META, None)
        game.toss_call_made = None
        _transition(game, GameStatus.TOSS_DECISION)
        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # TOSS DECISION — winning team chooses BAT or BOWL
    # ═══════════════════════════════════════════════════════════════════════════

    def submit_toss_decision(
        self,
        room: Room,
        player_id: str,
        decision: TossDecision,
    ) -> EngineResult:
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.TOSS_DECISION:
            return self._err(game, "Not awaiting toss decision")

        player = room.players.get(player_id)
        if player is None:
            return self._err(game, "Player not found")
        if player.team_id != game.toss_winner_team_id:
            return self._err(game, "Only the toss-winning team may choose bat or bowl")

        game.toss_decision = decision

        if decision == TossDecision.BAT:
            batting_team  = game.toss_winner_team_id
            bowling_team  = _other_team(batting_team)
        else:
            bowling_team  = game.toss_winner_team_id
            batting_team  = _other_team(bowling_team)

        # Build the public announcement string before setting up innings
        winner_team_name = room.teams.get(game.toss_winner_team_id or "", None)
        w_name = winner_team_name.name if winner_team_name else "Winning team"
        choice_word = "BAT" if decision == TossDecision.BAT else "BOWL"
        game.toss_announcement = f"{w_name} won the toss and chose to {choice_word} FIRST"

        _transition(game, GameStatus.INNINGS_SETUP)
        self._setup_innings(room, game, batting_team_id=batting_team, bowling_team_id=bowling_team)
        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # INNINGS SETUP  (internal — called from toss_decision and innings_break)
    # ═══════════════════════════════════════════════════════════════════════════

    def _setup_innings(
        self,
        room: Room,
        game: GameState,
        batting_team_id: str,
        bowling_team_id: str,
    ) -> None:
        """
        Build a fresh InningsState for the given batting/bowling teams.
        Sets total_wickets_available = number of batting-team players
        (+ 1 if that team has extra_wicket_available).
        Then transitions to CHOOSING_NUMBERS.
        """
        batting_team = room.teams[batting_team_id]
        bowling_team = room.teams[bowling_team_id]

        batting_player_ids = [
            pid for pid in batting_team.player_ids
            if pid in room.players and room.players[pid].connected
        ]
        if not batting_player_ids:
            raise ValueError("Batting team has no connected players")

        bowling_player_ids = [
            pid for pid in bowling_team.player_ids
            if pid in room.players and room.players[pid].connected
        ]
        if not bowling_player_ids:
            raise ValueError("Bowling team has no connected players")

        extra_wicket = batting_team.extra_wicket_available
        total_wickets = len(batting_player_ids) + (1 if extra_wicket else 0)

        innings = InningsState(
            batting_team_id=batting_team_id,
            bowling_team_id=bowling_team_id,
            batting_order=list(batting_player_ids),
            dismissed={pid: False for pid in batting_player_ids},
            current_batsman_idx=0,
            total_wickets_available=total_wickets,
            current_bowler_id=bowling_player_ids[0],
        )

        game.innings = innings
        # Clear any leftover ball/switch metadata
        game.__dict__.pop(_KEY_BALL_META, None)
        game.batsman_switch = None

        _transition(game, GameStatus.CHOOSING_NUMBERS)

    # ═══════════════════════════════════════════════════════════════════════════
    # CHOOSING NUMBERS — batsman and bowler each submit a hand number
    # ═══════════════════════════════════════════════════════════════════════════

    def submit_number(
        self,
        room: Room,
        player_id: str,
        number: int,
    ) -> EngineResult:
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.CHOOSING_NUMBERS:
            return self._err(
                game,
                f"Not accepting numbers right now (state={game.status.value})",
            )
        if game.innings is None:
            return self._err(game, "No active innings")

        innings = game.innings
        is_batsman = (player_id == innings.current_batsman_id)
        is_bowler  = (player_id == innings.current_bowler_id)

        if not (is_batsman or is_bowler):
            return self._err(game, "You are not the current batsman or bowler")

        meta: dict[str, int] = game.__dict__.setdefault(_KEY_BALL_META, {})
        role = "batsman" if is_batsman else "bowler"

        if role in meta:
            return self._err(game, "You have already submitted your number for this ball")

        meta[role] = number

        # Both submitted → resolve
        if "batsman" in meta and "bowler" in meta:
            return self._resolve_ball(room, game, meta["batsman"], meta["bowler"])

        # Still waiting for the other player
        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # BALL RESOLUTION  (internal)
    # ═══════════════════════════════════════════════════════════════════════════

    def _resolve_ball(
        self,
        room: Room,
        game: GameState,
        batsman_number: int,
        bowler_number: int,
    ) -> EngineResult:
        innings = game.innings
        assert innings is not None

        innings.total_balls += 1
        ball_result = resolve_ball(
            batsman_number=batsman_number,
            bowler_number=bowler_number,
            ball_number=innings.total_balls,
        )

        # Update player stats
        batsman_player = room.players.get(innings.current_batsman_id)
        bowler_player  = room.players.get(innings.current_bowler_id)
        if batsman_player:
            batsman_player.batting_stats.record_ball(ball_result.runs, ball_result.is_wicket)
        if bowler_player:
            bowler_player.bowling_stats.record_ball(ball_result.runs, ball_result.is_wicket)

        # Update innings score
        if not ball_result.is_wicket:
            innings.score += ball_result.runs

        # ── Store last ball for public display ───────────────────────────────
        innings.last_ball = ball_result
        innings.last_dismissed_name = None   # cleared on every non-wicket ball

        # Clear ball metadata for the next delivery
        game.__dict__.pop(_KEY_BALL_META, None)

        # ── Check target reached (2nd innings only) ───────────────────────────
        if (
            game.innings_number == 2
            and game.target is not None
            and is_target_reached(innings, game.target)
        ):
            game.status = GameStatus.RESOLVING_BALL
            return self._end_innings(room, game, ball_result)

        # ── Wicket ────────────────────────────────────────────────────────────
        if ball_result.is_wicket:
            innings.wickets += 1
            dismissed_name = batsman_player.display_name if batsman_player else "Batsman"
            innings.last_dismissed_name = dismissed_name
            if batsman_player:
                batsman_player.batting_stats.is_out    = True
                batsman_player.batting_stats.close_innings()
            innings.dismissed[innings.current_batsman_id] = True
            game.status = GameStatus.PLAYER_OUT

            # Does the innings end? (all wickets gone)
            if is_innings_complete(innings):
                return self._end_innings(room, game, ball_result)

            # Does extra-wicket voting kick in?
            if self._should_start_extra_wicket_vote(innings):
                return self._begin_extra_wicket_vote(room, game, ball_result)

            # Advance to the next batsman in the order
            self._advance_batsman(innings)
            game.status = GameStatus.CHOOSING_NUMBERS
            return self._ok(game, WSMessageType.PLAYER_OUT)

        # ── Normal ball scored ────────────────────────────────────────────────
        game.status = GameStatus.CHOOSING_NUMBERS
        return self._ok(game, WSMessageType.BALL_RESOLVED)

    # ─── Batting order helpers ─────────────────────────────────────────────────

    def _advance_batsman(self, innings: InningsState) -> None:
        """Move current_batsman_idx forward to the next undismissed batsman."""
        order = innings.batting_order
        idx   = innings.current_batsman_idx + 1
        while idx < len(order):
            if not innings.dismissed.get(order[idx], False):
                innings.current_batsman_idx = idx
                return
            idx += 1
        # No more batsmen in the normal order — innings should have ended via
        # is_innings_complete, but guard defensively.
        innings.current_batsman_idx = len(order)

    def _should_start_extra_wicket_vote(self, innings: InningsState) -> bool:
        """
        Returns True when:
          - the extra wicket is available and not yet used, AND
          - all regular batsmen are now dismissed (normal batting order exhausted)
        """
        if not innings.extra_wicket_used and innings.total_wickets_available > len(
            innings.batting_order
        ):
            all_dismissed = all(
                innings.dismissed.get(pid, False)
                for pid in innings.batting_order
            )
            return all_dismissed
        return False

    # ═══════════════════════════════════════════════════════════════════════════
    # EXTRA-WICKET VOTING
    # ═══════════════════════════════════════════════════════════════════════════

    def _begin_extra_wicket_vote(
        self,
        room: Room,
        game: GameState,
        last_ball: object | None = None,
    ) -> EngineResult:
        """Start round 1 of the extra-wicket voting."""
        innings = game.innings
        assert innings is not None

        eligible_voters = [
            p.id
            for p in room.players.values()
            if p.team_id == innings.batting_team_id and p.connected
        ]
        candidates = list(innings.batting_order)  # any normal player can re-bat

        game.extra_wicket_vote = ExtraWicketVoteState(
            round=1,
            eligible_voters=eligible_voters,
            candidates=candidates,
            votes={},
        )
        _transition(game, GameStatus.EXTRA_WICKET_VOTE)
        return self._ok(game, WSMessageType.EXTRA_WICKET_VOTE)

    def submit_extra_wicket_vote(
        self,
        room: Room,
        player_id: str,
        candidate_player_id: str,
    ) -> EngineResult:
        """Record one player's vote for who takes the extra wicket batting."""
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.EXTRA_WICKET_VOTE:
            return self._err(game, "No active extra-wicket vote")
        if game.extra_wicket_vote is None:
            return self._err(game, "Vote state missing")

        vote = game.extra_wicket_vote

        if player_id not in vote.eligible_voters:
            return self._err(game, "You are not eligible to vote in this round")
        if player_id in vote.votes:
            return self._err(game, "You have already voted in this round")
        if candidate_player_id not in vote.candidates:
            return self._err(
                game,
                f"'{candidate_player_id}' is not a valid candidate",
            )

        vote.votes[player_id] = candidate_player_id

        # Have all eligible voters voted?
        if set(vote.votes.keys()) >= set(vote.eligible_voters):
            return self._resolve_extra_wicket_vote(room, game)

        # Still waiting for more votes
        return self._ok(game, WSMessageType.EXTRA_WICKET_VOTE)

    def _resolve_extra_wicket_vote(
        self, room: Room, game: GameState
    ) -> EngineResult:
        """
        Tally votes.
        - Unique winner → that player bats the extra wicket.
        - Tie → start a new voting round (never randomly resolved).
        """
        vote = game.extra_wicket_vote
        assert vote is not None

        # Tally
        tally: dict[str, int] = {}
        for candidate in vote.votes.values():
            tally[candidate] = tally.get(candidate, 0) + 1

        max_votes = max(tally.values())
        winners = [pid for pid, cnt in tally.items() if cnt == max_votes]

        if len(winners) == 1:
            chosen = winners[0]
            innings = game.innings
            assert innings is not None

            innings.extra_wicket_batsman_id = chosen
            innings.extra_wicket_used        = False  # not yet — just assigned
            game.extra_wicket_vote           = None

            # The extra-wicket batsman steps in as the current batsman
            innings.batting_order.append(chosen)
            innings.dismissed[chosen] = False
            innings.current_batsman_idx = len(innings.batting_order) - 1

            game.status = GameStatus.CHOOSING_NUMBERS
            return self._ok(game, WSMessageType.GAME_STATE)
        else:
            # Tie — start a new round with only the tied candidates
            vote.round    += 1
            vote.votes     = {}
            vote.candidates = winners
            return self._ok(game, WSMessageType.EXTRA_WICKET_VOTE)

    # ═══════════════════════════════════════════════════════════════════════════
    # BOWLER SWITCHING
    # ═══════════════════════════════════════════════════════════════════════════

    def request_bowler_switch(
        self,
        room: Room,
        player_id: str,
        incoming_bowler_id: str,
    ) -> EngineResult:
        """
        A bowling-team player requests to become the current bowler.
        Multiple requests queue up; each is addressed in order after the
        current one is resolved.
        """
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status not in (GameStatus.CHOOSING_NUMBERS, GameStatus.BOWLER_SWITCH):
            return self._err(game, "Bowler switches can only be requested between balls")
        if game.innings is None:
            return self._err(game, "No active innings")

        innings = game.innings
        player   = room.players.get(player_id)
        incoming = room.players.get(incoming_bowler_id)

        if player is None or player.team_id != innings.bowling_team_id:
            return self._err(game, "Only bowling-team players may request a bowler switch")
        if incoming is None or incoming.team_id != innings.bowling_team_id:
            return self._err(game, "Incoming bowler must be on the bowling team")
        if incoming_bowler_id == innings.current_bowler_id:
            return self._err(game, "You are already bowling")
        if player_id != incoming_bowler_id:
            return self._err(game, "You can only request to bowl yourself")

        if game.status == GameStatus.BOWLER_SWITCH and game.bowler_switch is not None:
            # A switch is already open — add to queue if not already in it
            sw = game.bowler_switch
            if player_id == sw.requested_by or player_id in sw.queue:
                return self._err(game, "You have already requested a bowler switch")
            sw.queue.append(player_id)
            return self._ok(game, WSMessageType.BOWLER_SWITCH)

        # No open switch — open a new one
        game.bowler_switch = BowlerSwitchState(
            requested_by=player_id,
            current_bowler=innings.current_bowler_id,
            queue=[],
        )
        _transition(game, GameStatus.BOWLER_SWITCH)
        return self._ok(game, WSMessageType.BOWLER_SWITCH)

    def respond_bowler_switch(
        self,
        room: Room,
        player_id: str,
        accept: bool,
    ) -> EngineResult:
        """
        The current bowler accepts or declines.
        If accepted the requester becomes the bowler.
        If declined and there are queued requests, the next queued request
        becomes the active one; otherwise the state returns to CHOOSING_NUMBERS.
        """
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.BOWLER_SWITCH:
            return self._err(game, "No pending bowler switch")
        if game.bowler_switch is None:
            return self._err(game, "Bowler switch state missing")
        if game.innings is None:
            return self._err(game, "No active innings")

        switch  = game.bowler_switch
        innings = game.innings

        if player_id != switch.current_bowler:
            return self._err(game, "Only the current bowler can respond to a switch request")

        if accept:
            innings.current_bowler_id = switch.requested_by
            game.bowler_switch = None
            _transition(game, GameStatus.CHOOSING_NUMBERS)
        else:
            # Declined — move to next queued request if any
            if switch.queue:
                next_requester = switch.queue.pop(0)
                switch.requested_by = next_requester
                # current_bowler stays the same (they must also accept/decline the next)
            else:
                game.bowler_switch = None
                _transition(game, GameStatus.CHOOSING_NUMBERS)

        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # BATSMAN SWITCHING (bowling team requests; current batsman decides)
    # ═══════════════════════════════════════════════════════════════════════════

    def request_batsman_switch(
        self,
        room: Room,
        player_id: str,
    ) -> EngineResult:
        """
        A batting-team player (who is NOT the current batsman and is not out)
        requests to swap in as the current batsman.  The current batsman sees
        all pending requests and chooses to accept or decline.

        Multiple batting-team players can each request independently; all
        their names are shown to the current batsman at once.
        """
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.CHOOSING_NUMBERS:
            return self._err(game, "Batsman switches can only be requested between balls")
        if game.innings is None:
            return self._err(game, "No active innings")

        innings = game.innings
        player  = room.players.get(player_id)

        # Must be on the batting team
        if player is None or player.team_id != innings.batting_team_id:
            return self._err(game, "Only batting-team players may request a batsman switch")

        # Must not be the current batsman
        if player_id == innings.current_batsman_id:
            return self._err(game, "You are already batting")

        # Must not be dismissed
        if innings.dismissed.get(player_id, False):
            return self._err(game, "You have been dismissed and cannot request to bat again")

        if game.batsman_switch is None:
            game.batsman_switch = BatsmanSwitchState(
                current_batsman=innings.current_batsman_id,
                requests=[player_id],
            )
        else:
            sw = game.batsman_switch
            if player_id in sw.requests:
                return self._err(game, "You have already requested a batsman switch")
            sw.requests.append(player_id)

        return self._ok(game, WSMessageType.GAME_STATE)

    def respond_batsman_switch(
        self,
        room: Room,
        player_id: str,
        accept: bool,
        chosen_player_id: str | None = None,
    ) -> EngineResult:
        """
        The current batsman responds to switch requests.

        - accept=False  → clear all requests, play continues normally.
        - accept=True   → chosen_player_id steps in as the current batsman
                          (must be one of the requesters and must not be dismissed).
                          The current batsman stays in the order but steps back;
                          they can bat again later when their turn comes.
        If only one request exists, chosen_player_id defaults to that requester.
        """
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.batsman_switch is None:
            return self._err(game, "No pending batsman switch request")
        if game.innings is None:
            return self._err(game, "No active innings")

        innings = game.innings
        sw      = game.batsman_switch

        if player_id != sw.current_batsman:
            return self._err(game, "Only the current batsman can respond to a switch request")

        game.batsman_switch = None

        if not accept:
            return self._ok(game, WSMessageType.GAME_STATE)

        # Determine who steps in
        if chosen_player_id is None:
            if len(sw.requests) == 1:
                chosen_player_id = sw.requests[0]
            else:
                # Accept without specifying: pick the first requester
                chosen_player_id = sw.requests[0]

        if chosen_player_id not in sw.requests:
            return self._err(game, "Chosen player did not request a switch")

        chosen_player = room.players.get(chosen_player_id)
        if chosen_player is None:
            return self._err(game, "Chosen player not found")
        if innings.dismissed.get(chosen_player_id, False):
            return self._err(game, "Chosen player has already been dismissed")

        # Swap: put chosen_player_id at the current batsman slot
        # Move current batsman's index to right after chosen in the order,
        # so they still bat later when it's their turn again.
        current_id = innings.current_batsman_id

        # Remove chosen from their current position in the order (if present)
        if chosen_player_id in innings.batting_order:
            innings.batting_order.remove(chosen_player_id)

        # Insert chosen immediately at the current index (they bat now)
        innings.batting_order.insert(innings.current_batsman_idx, chosen_player_id)

        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # END OF INNINGS
    # ═══════════════════════════════════════════════════════════════════════════

    def _end_innings(
        self,
        room: Room,
        game: GameState,
        last_ball: object | None = None,
    ) -> EngineResult:
        """
        Snapshot the current innings into history and transition to the next phase:
          - 1st innings → INNINGS_BREAK
          - 2nd innings → GAME_OVER
        """
        innings = game.innings
        assert innings is not None

        # Finalise batting stats for any not-yet-closed batsmen
        for pid in innings.batting_order:
            player = room.players.get(pid)
            if player and not player.batting_stats.is_out:
                player.batting_stats.close_innings()

        history = InningsHistory(
            innings_number=game.innings_number,
            batting_team_id=innings.batting_team_id,
            bowling_team_id=innings.bowling_team_id,
            score=innings.score,
            wickets=innings.wickets,
            completed=True,
        )
        game.innings_history.append(history)

        if game.innings_number == 1:
            # TARGET = first innings score + 1
            game.target = innings.score + 1
            game.innings = innings  # preserve for display; overwritten at 2nd innings setup
            _transition(game, GameStatus.INNINGS_BREAK)
            return self._ok(game, WSMessageType.INNINGS_COMPLETE)
        else:
            result = calculate_result(room, game)
            game.final_result = result

            # ── Match over: release the room back to post-game state ──────────
            # room_status FINISHED unblocks ready-up / team switch / new joins,
            # and clearing ready flags means nobody carries stale "ready"
            # status from the finished match into the lobby.
            room.room_status = RoomStatus.FINISHED
            for p in room.players.values():
                p.ready = False

            _transition(game, GameStatus.GAME_OVER)
            return self._ok(game, WSMessageType.GAME_OVER)

    # ═══════════════════════════════════════════════════════════════════════════
    # INNINGS BREAK → SECOND INNINGS
    # ═══════════════════════════════════════════════════════════════════════════

    def start_second_innings(self, room: Room) -> EngineResult:
        """
        Triggered when either team player sends START_SECOND_INNINGS after the
        innings-break screen.  Swaps batting/bowling roles, resets per-innings
        state, and re-enters CHOOSING_NUMBERS.
        """
        game = self._need_game(room)
        if game is None:
            return self._err(None, "No active game")
        if game.status != GameStatus.INNINGS_BREAK:
            return self._err(game, "Not in innings break")

        assert game.innings is not None
        first_batting  = game.innings.batting_team_id
        first_bowling  = game.innings.bowling_team_id

        # Swap roles
        new_batting  = first_bowling
        new_bowling  = first_batting

        game.innings_number = 2
        game.__dict__.pop(_KEY_BALL_META, None)
        game.batsman_switch = None

        _transition(game, GameStatus.SECOND_INNINGS)
        self._setup_innings(room, game, batting_team_id=new_batting, bowling_team_id=new_bowling)
        return self._ok(game, WSMessageType.GAME_STATE)

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _need_game(room: Room) -> GameState | None:
        return room.game

    @staticmethod
    def _err(game: GameState | None, message: str) -> EngineResult:
        return EngineResult(
            success=False,
            event=WSMessageType.ERROR,
            game=game if game is not None else GameState(),
            error=message,
        )

    @staticmethod
    def _ok(game: GameState, event: WSMessageType) -> EngineResult:
        """Bump the state version and return a successful EngineResult."""
        bump_version(game)
        return EngineResult(success=True, event=event, game=game)


def _other_team(team_id: str) -> str:
    return "team_b" if team_id == "team_a" else "team_a"


# Module-level singleton imported by services
engine = GameEngine()
