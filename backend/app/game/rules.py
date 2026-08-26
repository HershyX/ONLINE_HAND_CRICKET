"""
Hand Cricket rules — pure functions, zero I/O, zero FastAPI.

All game decisions flow through here.  The engine calls these; tests call
them directly.  Nothing here knows about WebSockets, rooms, or services.
"""

from __future__ import annotations

from app.models.domain import (
    BallResult,
    FinalResult,
    GameState,
    InningsState,
    Room,
    TossCall,
)


# ─── Toss ─────────────────────────────────────────────────────────────────────


def resolve_toss(
    caller_id: str,
    other_id: str,
    caller_call: TossCall,
    caller_number: int,
    other_number: int,
) -> str:
    """
    Return the player_id of the toss winner.

    Both players reveal a number (0-10).  The caller has already chosen
    ODD or EVEN.  The sum of the two numbers determines the outcome:
        ODD sum  → ODD-caller wins
        EVEN sum → EVEN-caller wins  (0 + 0 = 0 is EVEN)
    """
    total = caller_number + other_number
    is_odd = (total % 2) == 1
    caller_wins = (caller_call == TossCall.ODD and is_odd) or (
        caller_call == TossCall.EVEN and not is_odd
    )
    return caller_id if caller_wins else other_id


# ─── Ball resolution ──────────────────────────────────────────────────────────


def resolve_ball(
    batsman_number: int,
    bowler_number: int,
    ball_number: int,
) -> BallResult:
    """
    Resolve a single delivery.

    Numbers allowed: 0–10 inclusive.

    Rules (in priority order):
        1. batsman == bowler          → OUT (runs = 0)
        2. batsman == 0, bowler != 0  → runs = bowler_number  (zero special rule)
        3. otherwise                  → runs = batsman_number

    Raises ValueError for numbers outside 0-10.
    """
    if not (0 <= batsman_number <= 10):
        raise ValueError(f"Invalid batsman number: {batsman_number} (must be 0-10)")
    if not (0 <= bowler_number <= 10):
        raise ValueError(f"Invalid bowler number: {bowler_number} (must be 0-10)")

    # Rule 1: matching → wicket
    if batsman_number == bowler_number:
        return BallResult(
            batsman_number=batsman_number,
            bowler_number=bowler_number,
            runs=0,
            is_wicket=True,
            ball_number=ball_number,
        )

    # Rule 2: batsman plays 0, bowler plays non-zero → bowler's number scores
    if batsman_number == 0:
        return BallResult(
            batsman_number=batsman_number,
            bowler_number=bowler_number,
            runs=bowler_number,
            is_wicket=False,
            ball_number=ball_number,
        )

    # Rule 3: normal scoring
    return BallResult(
        batsman_number=batsman_number,
        bowler_number=bowler_number,
        runs=batsman_number,
        is_wicket=False,
        ball_number=ball_number,
    )


# ─── Innings completion ───────────────────────────────────────────────────────


def is_innings_complete(innings: InningsState) -> bool:
    """
    An innings ends ONLY when all available wickets are exhausted.

    There is no over limit and no ball limit.

    total_wickets_available = number of batsmen on the batting team
                              + 1 if that team has an extra wicket.

    The engine sets total_wickets_available before the innings starts.
    """
    return innings.all_wickets_down


def is_target_reached(innings: InningsState, target: int) -> bool:
    """True when the chasing team's score meets or exceeds the target."""
    return innings.score >= target


# ─── Result calculation ───────────────────────────────────────────────────────


def calculate_result(room: Room, game: GameState) -> FinalResult:
    """
    Determine the final match result after both innings are complete.
    Requires game.innings_history to have exactly two completed entries.
    """
    if len(game.innings_history) < 2:
        raise ValueError("Cannot calculate result: both innings must be complete")

    inn1 = game.innings_history[0]
    inn2 = game.innings_history[1]

    first_team_id  = inn1.batting_team_id
    second_team_id = inn2.batting_team_id
    first_score    = inn1.score
    second_score   = inn2.score

    # ── MVP: composite score ──────────────────────────────────────────────────
    #
    # Batting contribution:
    #   runs_scored  (raw)
    #
    # Bowling contribution:
    #   wickets_taken × BASE_PER_WICKET
    #   + economy_bonus: bowlers who concede fewer runs per wicket are rewarded.
    #     bowling_average = runs_conceded / wickets_taken  (lower = better)
    #     If bowling_average ≤ 5  → +15 bonus per wicket
    #     If bowling_average ≤ 10 → +10 bonus per wicket
    #     If bowling_average ≤ 15 → +5  bonus per wicket
    #     Otherwise                → +0
    #
    # This naturally favours:
    #   - High-scoring batsmen over low scorers.
    #   - Bowlers who take many wickets over few.
    #   - Bowlers who give away few runs per wicket over those who are expensive.

    BASE_PER_WICKET = 20

    mvp_id: str | None = None
    best = -1.0

    for player in room.players.values():
        bs = player.batting_stats
        bw = player.bowling_stats

        batting_score = float(bs.runs_scored)

        bowling_score = 0.0
        if bw.wickets_taken > 0:
            avg = bw.runs_conceded / bw.wickets_taken   # bowling average (lower = better)
            if avg <= 5:
                economy_bonus = 15
            elif avg <= 10:
                economy_bonus = 10
            elif avg <= 15:
                economy_bonus = 5
            else:
                economy_bonus = 0
            bowling_score = bw.wickets_taken * (BASE_PER_WICKET + economy_bonus)

        total = batting_score + bowling_score
        if total > best:
            best = total
            mvp_id = player.id

    # Wickets remaining for 2nd-innings batting team
    second_innings_state = game.innings  # may be None after game_over; use history
    wickets_remaining: int | None = None
    if second_innings_state is not None:
        wickets_remaining = second_innings_state.wickets_remaining

    if second_score > first_score:
        return FinalResult(
            winner_team_id=second_team_id,
            margin_wickets=wickets_remaining,
            is_tie=False,
            mvp_player_id=mvp_id,
        )
    if first_score > second_score:
        return FinalResult(
            winner_team_id=first_team_id,
            margin_runs=first_score - second_score,
            is_tie=False,
            mvp_player_id=mvp_id,
        )
    return FinalResult(
        winner_team_id=None,
        is_tie=True,
        mvp_player_id=mvp_id,
    )
