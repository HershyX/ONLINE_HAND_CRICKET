"""
Core domain models for Hand Cricket.

Pure Pydantic models — no FastAPI, no WebSocket, no database logic.
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─── Enumerations ─────────────────────────────────────────────────────────────


class GameStatus(str, Enum):
    LOBBY             = "LOBBY"
    TOSS              = "TOSS"
    TOSS_DECISION     = "TOSS_DECISION"
    INNINGS_SETUP     = "INNINGS_SETUP"
    CHOOSING_NUMBERS  = "CHOOSING_NUMBERS"
    RESOLVING_BALL    = "RESOLVING_BALL"
    PLAYER_OUT        = "PLAYER_OUT"
    # Extra-wicket voting: smaller team votes for who takes the extra bat
    EXTRA_WICKET_VOTE = "EXTRA_WICKET_VOTE"
    # Bowler-switch: current bowler must accept/decline a switch request
    BOWLER_SWITCH     = "BOWLER_SWITCH"
    INNINGS_BREAK     = "INNINGS_BREAK"
    SECOND_INNINGS    = "SECOND_INNINGS"
    GAME_OVER         = "GAME_OVER"


class RoomStatus(str, Enum):
    WAITING   = "WAITING"
    READY     = "READY"
    IN_GAME   = "IN_GAME"
    FINISHED  = "FINISHED"


class TossDecision(str, Enum):
    BAT  = "BAT"
    BOWL = "BOWL"


class TossCall(str, Enum):
    ODD  = "ODD"
    EVEN = "EVEN"


# ─── Player statistics ────────────────────────────────────────────────────────


class BattingStats(BaseModel):
    runs_scored:   int  = 0
    balls_faced:   int  = 0
    fours:         int  = 0
    sixes:         int  = 0
    is_out:        bool = False
    highest_score: int  = 0
    innings_count: int  = 0

    def record_ball(self, runs: int, is_wicket: bool) -> None:
        self.balls_faced += 1
        if is_wicket:
            self.is_out = True
        else:
            self.runs_scored += runs
            if runs == 4:
                self.fours += 1
            elif runs == 6:
                self.sixes += 1

    def close_innings(self) -> None:
        """Call at end of each batting innings to lock highest_score."""
        self.innings_count += 1
        if self.runs_scored > self.highest_score:
            self.highest_score = self.runs_scored

    @property
    def strike_rate(self) -> float:
        if self.balls_faced == 0:
            return 0.0
        return round((self.runs_scored / self.balls_faced) * 100, 2)


class BowlingStats(BaseModel):
    balls_bowled:   int = 0
    runs_conceded:  int = 0
    wickets_taken:  int = 0

    def record_ball(self, runs: int, is_wicket: bool) -> None:
        self.balls_bowled += 1
        if is_wicket:
            self.wickets_taken += 1
        else:
            self.runs_conceded += runs

    @property
    def economy(self) -> float:
        if self.balls_bowled == 0:
            return 0.0
        return round(self.runs_conceded / (self.balls_bowled / 6), 2)


# ─── Player ───────────────────────────────────────────────────────────────────


class Player(BaseModel):
    id:            str
    display_name:  str
    team_id:       Optional[str]  = None
    ready:         bool           = False
    connected:     bool           = True
    batting_stats: BattingStats   = Field(default_factory=BattingStats)
    bowling_stats: BowlingStats   = Field(default_factory=BowlingStats)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 20:
            raise ValueError("Display name must be 2–20 characters")
        return v


# ─── Team ─────────────────────────────────────────────────────────────────────


class Team(BaseModel):
    id:                     str
    name:                   str
    player_ids:             list[str]  = Field(default_factory=list)
    score:                  int        = 0
    wickets:                int        = 0
    extra_wicket_available: bool       = False


# ─── Ball result ──────────────────────────────────────────────────────────────


class BallResult(BaseModel):
    batsman_number: int
    bowler_number:  int
    runs:           int
    is_wicket:      bool
    ball_number:    int   # sequential within the innings (1-based)


# ─── Extra-wicket voting state ────────────────────────────────────────────────


class ExtraWicketVoteState(BaseModel):
    """
    Tracks one round of voting for who takes the extra batting opportunity.
    Eligible voters are all connected players on the smaller team.
    """
    round:          int                  = 1
    eligible_voters: list[str]           = Field(default_factory=list)
    # player_id → voted_for player_id
    votes:          dict[str, str]       = Field(default_factory=dict)
    # candidates: player_ids eligible to bat
    candidates:     list[str]            = Field(default_factory=list)


# ─── Bowler-switch state ──────────────────────────────────────────────────────


class BowlerSwitchState(BaseModel):
    """
    Tracks a pending bowler-switch request + a queue of further requests.
    The current bowler must accept or decline.
    """
    requested_by:   str        # player_id who wants to bowl next
    current_bowler: str        # player_id of the current bowler who must respond
    # Queue of additional player_ids who also want to bowl (FIFO)
    queue:          list[str]  = Field(default_factory=list)


# ─── Batsman-switch state ─────────────────────────────────────────────────────


class BatsmanSwitchState(BaseModel):
    """
    Multiple bowling-team players may request the current batsman be switched
    (replaced by the next in order).  The current batsman decides who, if anyone.
    """
    # All player_ids who have requested the switch (deduplicated, ordered)
    requests:         list[str] = Field(default_factory=list)
    # The current batsman who must accept or decline
    current_batsman:  str       = ""


# ─── Innings-level state (reset each innings) ─────────────────────────────────


class InningsState(BaseModel):
    """
    Mutable state that belongs to a single innings.
    Kept inside GameState; replaced wholesale at innings switch.
    """
    batting_team_id:    str
    bowling_team_id:    str

    # Batting order: list of player_ids in bat order
    batting_order:      list[str]            = Field(default_factory=list)
    # Which batsmen have been dismissed (player_id → True)
    dismissed:          dict[str, bool]      = Field(default_factory=dict)
    # Current batsman index into batting_order
    current_batsman_idx: int                 = 0
    # Player chosen for the extra wicket (None until voted in)
    extra_wicket_batsman_id: Optional[str]   = None
    # Has the extra wicket opportunity been used?
    extra_wicket_used:  bool                 = False

    # Score tracking
    score:              int   = 0
    wickets:            int   = 0      # normal dismissals
    total_balls:        int   = 0

    # Current bowler
    current_bowler_id:  str   = ""

    # How many wickets are available total (set at innings start)
    total_wickets_available: int = 0

    # Last resolved ball — shown publicly after each delivery
    last_ball:          Optional[BallResult] = None

    # Name of the last dismissed player (for the wicket popup)
    last_dismissed_name: Optional[str]       = None

    @property
    def current_batsman_id(self) -> str:
        if self.current_batsman_idx < len(self.batting_order):
            return self.batting_order[self.current_batsman_idx]
        return ""

    @property
    def all_wickets_down(self) -> bool:
        return self.wickets_used >= self.total_wickets_available

    @property
    def wickets_used(self) -> int:
        """Normal dismissals + extra wicket if used."""
        return self.wickets + (1 if self.extra_wicket_used else 0)

    @property
    def wickets_remaining(self) -> int:
        return max(0, self.total_wickets_available - self.wickets_used)


# ─── Innings history ──────────────────────────────────────────────────────────


class InningsHistory(BaseModel):
    innings_number:  int
    batting_team_id: str
    bowling_team_id: str
    score:           int              = 0
    wickets:         int              = 0
    balls:           list[BallResult] = Field(default_factory=list)
    completed:       bool             = False


# ─── Final result ─────────────────────────────────────────────────────────────


class FinalResult(BaseModel):
    winner_team_id:   Optional[str] = None
    margin_runs:      Optional[int] = None
    margin_wickets:   Optional[int] = None
    is_tie:           bool          = False
    mvp_player_id:    Optional[str] = None


# ─── Game state ───────────────────────────────────────────────────────────────


class GameState(BaseModel):
    status:          GameStatus  = GameStatus.LOBBY
    innings_number:  int         = 1

    # Monotonically increasing version — incremented on every authoritative change.
    # Clients must discard any event whose version is not strictly greater than
    # the last version they applied.
    state_version:   int         = 0

    # Toss
    toss_winner_team_id: Optional[str]      = None   # team_a / team_b
    toss_caller_player_id: Optional[str]    = None   # player who called ODD/EVEN
    toss_responder_player_id: Optional[str] = None   # other team's representative
    toss_call_made:  Optional[TossCall]     = None   # call revealed once submitted
    toss_decision:   Optional[TossDecision] = None
    # Both numbers revealed publicly after toss resolves
    toss_caller_number:    Optional[int]    = None
    toss_responder_number: Optional[int]    = None
    # Human-readable announcement shown to all after toss decision (e.g.
    # "Team 1 won the toss and chose to BAT FIRST")
    toss_announcement: Optional[str]        = None

    # Active innings (replaced at innings switch)
    innings:         Optional[InningsState] = None

    # Target for 2nd innings (set when 1st innings ends)
    target:          Optional[int]          = None

    # History
    innings_history: list[InningsHistory]   = Field(default_factory=list)
    final_result:    Optional[FinalResult]  = None

    # Pending sub-states (only one active at a time)
    extra_wicket_vote: Optional[ExtraWicketVoteState] = None
    bowler_switch:     Optional[BowlerSwitchState]    = None
    batsman_switch:    Optional[BatsmanSwitchState]   = None

    # Convenience properties (shortcuts into active innings)
    @property
    def score(self) -> int:
        return self.innings.score if self.innings else 0

    @property
    def wickets(self) -> int:
        return self.innings.wickets if self.innings else 0

    @property
    def current_batsman_id(self) -> str:
        return self.innings.current_batsman_id if self.innings else ""

    @property
    def current_bowler_id(self) -> str:
        return self.innings.current_bowler_id if self.innings else ""

    @property
    def batting_team_id(self) -> Optional[str]:
        return self.innings.batting_team_id if self.innings else None

    @property
    def bowling_team_id(self) -> Optional[str]:
        return self.innings.bowling_team_id if self.innings else None

    @property
    def total_balls_bowled(self) -> int:
        return self.innings.total_balls if self.innings else 0


# ─── Room ─────────────────────────────────────────────────────────────────────


def _generate_room_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Room(BaseModel):
    room_code:   str        = Field(default_factory=lambda: _generate_room_code())
    host_id:     str
    players:     dict[str, Player]  = Field(default_factory=dict)
    teams:       dict[str, Team]    = Field(default_factory=dict)
    room_status: RoomStatus         = RoomStatus.WAITING
    game:        Optional[GameState] = None
    max_players: int                = 10
    created_at:  datetime           = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Chat history — kept for reconnect snapshot (capped at last 100 messages)
    chat_messages: list["ChatMessage"] = Field(default_factory=list)

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]

    def all_ready(self) -> bool:
        connected = self.connected_players()
        return len(connected) >= 2 and all(p.ready for p in connected)

    def is_full(self) -> bool:
        return len(self.connected_players()) >= self.max_players

    def players_in_team(self, team_id: str) -> list[Player]:
        return [p for p in self.players.values() if p.team_id == team_id]

    def connected_players_in_team(self, team_id: str) -> list[Player]:
        return [p for p in self.players.values()
                if p.team_id == team_id and p.connected]

    def team_counts(self) -> tuple[int, int]:
        """Returns (team_a_count, team_b_count) of connected players."""
        a = sum(1 for p in self.players.values()
                if p.connected and p.team_id == "team_a")
        b = sum(1 for p in self.players.values()
                if p.connected and p.team_id == "team_b")
        return a, b


# ─── WebSocket message envelope ───────────────────────────────────────────────


class WSMessageType(str, Enum):
    # ── Server → Client ──────────────────────────────────────────────────────
    ROOM_STATE          = "ROOM_STATE"
    PLAYER_JOINED       = "PLAYER_JOINED"
    PLAYER_LEFT         = "PLAYER_LEFT"
    PLAYER_UPDATED      = "PLAYER_UPDATED"
    PLAYER_READY        = "PLAYER_READY"
    READY_STATE_CHANGED = "READY_STATE_CHANGED"
    TEAM_UPDATED        = "TEAM_UPDATED"
    GAME_STATE          = "GAME_STATE"
    GAME_STARTED        = "GAME_STARTED"
    BALL_RESOLVED       = "BALL_RESOLVED"
    PLAYER_OUT          = "PLAYER_OUT"
    INNINGS_COMPLETE    = "INNINGS_COMPLETE"
    EXTRA_WICKET_VOTE   = "EXTRA_WICKET_VOTE"
    BOWLER_SWITCH       = "BOWLER_SWITCH"
    GAME_OVER           = "GAME_OVER"
    ERROR               = "ERROR"
    PING                = "PING"
    # ── Client → Server ──────────────────────────────────────────────────────
    JOIN_ROOM              = "JOIN_ROOM"
    SET_READY              = "SET_READY"
    UPDATE_NAME            = "UPDATE_NAME"
    SWITCH_TEAM            = "SWITCH_TEAM"
    START_MATCH            = "START_MATCH"
    TRANSFER_HOST          = "TRANSFER_HOST"
    CHAT_MESSAGE           = "CHAT_MESSAGE"
    RETURN_TO_LOBBY        = "RETURN_TO_LOBBY"
    TOSS_CALL              = "TOSS_CALL"
    TOSS_RESPONSE          = "TOSS_RESPONSE"
    TOSS_DECISION          = "TOSS_DECISION"
    CHOOSE_NUMBER          = "CHOOSE_NUMBER"
    VOTE_EXTRA_WICKET      = "VOTE_EXTRA_WICKET"
    REQUEST_BOWLER_SWITCH  = "REQUEST_BOWLER_SWITCH"
    RESPOND_BOWLER_SWITCH  = "RESPOND_BOWLER_SWITCH"
    REQUEST_BATSMAN_SWITCH = "REQUEST_BATSMAN_SWITCH"
    RESPOND_BATSMAN_SWITCH = "RESPOND_BATSMAN_SWITCH"
    START_SECOND_INNINGS   = "START_SECOND_INNINGS"
    PONG                   = "PONG"


class WSMessage(BaseModel):
    type:      WSMessageType
    payload:   dict           = Field(default_factory=dict)
    timestamp: str            = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    player_id: Optional[str] = None


# ─── Action payloads (Client → Server) ───────────────────────────────────────


class SetReadyPayload(BaseModel):
    ready: bool


class TossCallPayload(BaseModel):
    call: TossCall
    number: int

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: int) -> int:
        if not (0 <= v <= 10):
            raise ValueError("Toss number must be between 0 and 10")
        return v


class TossResponsePayload(BaseModel):
    number: int

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: int) -> int:
        if not (0 <= v <= 10):
            raise ValueError("Toss number must be between 0 and 10")
        return v


class TossDecisionPayload(BaseModel):
    decision: TossDecision


class ChooseNumberPayload(BaseModel):
    number: int

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: int) -> int:
        if not (0 <= v <= 10):
            raise ValueError("Hand number must be between 0 and 10")
        return v


class VoteExtraWicketPayload(BaseModel):
    candidate_player_id: str


class RespondBowlerSwitchPayload(BaseModel):
    accept: bool


class RequestBowlerSwitchPayload(BaseModel):
    incoming_bowler_id: str


class RequestBatsmanSwitchPayload(BaseModel):
    """A bowling-team player requests the current batsman be replaced."""
    # No extra fields needed — the requester identity comes from player_id in the WS context.
    pass


class RespondBatsmanSwitchPayload(BaseModel):
    """The current batsman accepts or declines. When accepting with multiple
    requesters, optionally specify which one steps in (defaults to first)."""
    accept: bool
    chosen_player_id: Optional[str] = None


class UpdateNamePayload(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 20:
            raise ValueError("Display name must be 2–20 characters")
        return v


class SwitchTeamPayload(BaseModel):
    team_id: str  # "team_a" | "team_b"


class TransferHostPayload(BaseModel):
    new_host_id: str


class ChatMessagePayload(BaseModel):
    """Sent by a client to broadcast a chat message."""
    content: str
    scope:   str  # "global" | "team"

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 200:
            raise ValueError("Message must be 200 characters or fewer")
        return v


# ─── Chat message (stored in room, broadcast to clients) ─────────────────────


class ChatMessage(BaseModel):
    id:           str   # uuid
    player_id:    str
    display_name: str
    team_id:      Optional[str]
    scope:        str   # "global" | "team"
    content:      str
    timestamp:    str


# ─── Start-match validation ───────────────────────────────────────────────────


class StartMatchValidation(BaseModel):
    can_start: bool
    reasons:   list[str] = Field(default_factory=list)


# ─── Team-size helpers (pure functions) ──────────────────────────────────────


def bump_version(game: "GameState") -> None:
    """Increment the state version on every authoritative mutation."""
    game.state_version += 1


def validate_team_sizes(team_a_count: int, team_b_count: int) -> Optional[str]:
    if team_a_count == 0 or team_b_count == 0:
        return "Both teams must have at least one player"
    diff = abs(team_a_count - team_b_count)
    if diff > 1:
        return (
            f"Team sizes too unequal ({team_a_count} vs {team_b_count}). "
            "The difference must be at most 1."
        )
    return None


def compute_extra_wicket(team_a_count: int, team_b_count: int) -> tuple[bool, bool]:
    """Returns (team_a_gets_extra, team_b_gets_extra)."""
    diff = team_a_count - team_b_count
    if diff == 1:
        return False, True
    if diff == -1:
        return True, False
    return False, False
