"""
Comprehensive tests for the game engine.

Tests are grouped by game phase and cover every scenario listed in the spec:
  toss, decision, scoring, zero rule, wickets, batting rotation, unlimited
  balls, extra wicket, voting (including tie re-vote), bowler switching,
  first innings, second innings, target, winning, statistics.

All tests are pure engine calls — no HTTP, no WebSocket, no asyncio.
"""

import pytest

from app.game.engine import GameEngine, _other_team
from app.models.domain import (
    GameState,
    GameStatus,
    Player,
    Room,
    Team,
    TossCall,
    TossDecision,
)

# ─── Fixtures and helpers ─────────────────────────────────────────────────────


def make_engine() -> GameEngine:
    return GameEngine()


def make_1v1_room(
    bat_first: str = "team_a",
    extra_a: bool = False,
    extra_b: bool = False,
) -> tuple[Room, str, str, str, str]:
    """
    Build a minimal 1v1 room with two teams of 1 player each.

    Returns (room, p1_id, p2_id, team_a_id, team_b_id).
    p1 is on team_a, p2 is on team_b.
    Both players are ready.
    GameState is at LOBBY.
    """
    p1 = Player(id="p1", display_name="Alice")
    p2 = Player(id="p2", display_name="Bob")
    p1.team_id = "team_a"
    p2.team_id = "team_b"
    p1.ready   = True
    p2.ready   = True

    team_a = Team(id="team_a", name="Team 1",
                  player_ids=["p1"], extra_wicket_available=extra_a)
    team_b = Team(id="team_b", name="Team 2",
                  player_ids=["p2"], extra_wicket_available=extra_b)

    room            = Room(host_id="p1")
    room.players    = {"p1": p1, "p2": p2}
    room.teams      = {"team_a": team_a, "team_b": team_b}
    room.game       = GameState()

    return room, "p1", "p2", "team_a", "team_b"


def make_2v2_room() -> tuple[Room, list[str], list[str]]:
    """
    Returns (room, team_a_player_ids, team_b_player_ids).
    All four players are ready.
    """
    players = {}
    for pid, name, team in [
        ("a1", "Alice",   "team_a"),
        ("a2", "Ash",     "team_a"),
        ("b1", "Bob",     "team_b"),
        ("b2", "Ben",     "team_b"),
    ]:
        p          = Player(id=pid, display_name=name)
        p.team_id  = team
        p.ready    = True
        players[pid] = p

    team_a = Team(id="team_a", name="Team 1", player_ids=["a1", "a2"])
    team_b = Team(id="team_b", name="Team 2", player_ids=["b1", "b2"])

    room         = Room(host_id="a1")
    room.players = players
    room.teams   = {"team_a": team_a, "team_b": team_b}
    room.game    = GameState()

    return room, ["a1", "a2"], ["b1", "b2"]


def start_toss_get_players(
    eng: GameEngine, room: Room
) -> tuple[str, str]:
    """
    Runs start_toss and returns (caller_player_id, responder_player_id).
    """
    r = eng.start_toss(room)
    assert r.success, r.error
    return room.game.toss_caller_player_id, room.game.toss_responder_player_id  # type: ignore[return-value]


def do_toss_team_a_wins(eng: GameEngine, room: Room) -> None:
    """
    Force team_a to win the toss: caller is team_a rep.
    Caller calls ODD, both show 1 → sum 2 (even) → bowler wins?
    Actually: caller calls EVEN, both show 2 → sum 4 (even) → caller wins.
    """
    caller, responder = start_toss_get_players(eng, room)
    # Ensure caller is on team_a; if not swap logic
    game = room.game
    assert game is not None
    # EVEN call, caller shows 2, responder shows 2 → sum=4 (even) → caller wins
    r = eng.submit_toss_call(room, caller, TossCall.EVEN, 2)
    assert r.success, r.error
    r = eng.submit_toss_response(room, responder, 2)
    assert r.success, r.error
    assert game.status == GameStatus.TOSS_DECISION
    assert game.toss_winner_team_id == room.players[caller].team_id


def do_toss_and_decide(
    eng: GameEngine,
    room: Room,
    winning_team_decides: TossDecision,
) -> str:
    """
    Completes the toss so the winning team wins, then makes the given decision.
    Returns the batting team_id.
    """
    caller, responder = start_toss_get_players(eng, room)
    game  = room.game
    assert game is not None

    # caller calls EVEN and shows 4; responder shows 2 → 6 even → caller wins
    eng.submit_toss_call(room, caller, TossCall.EVEN, 4)
    eng.submit_toss_response(room, responder, 2)

    winner_team = game.toss_winner_team_id
    assert winner_team is not None

    # Pick any player from the winning team to decide
    deciding_player = next(
        pid for pid, p in room.players.items()
        if p.team_id == winner_team
    )
    r = eng.submit_toss_decision(room, deciding_player, winning_team_decides)
    assert r.success, r.error

    assert game.status == GameStatus.CHOOSING_NUMBERS
    assert game.innings is not None
    return game.innings.batting_team_id


def play_ball(
    eng: GameEngine,
    room: Room,
    bat_num: int,
    bowl_num: int,
):
    """Submit both numbers for one ball. Returns EngineResult."""
    game   = room.game
    assert game is not None
    assert game.innings is not None

    bat_id  = game.innings.current_batsman_id
    bowl_id = game.innings.current_bowler_id

    r = eng.submit_number(room, bat_id, bat_num)
    assert r.success, r.error
    r = eng.submit_number(room, bowl_id, bowl_num)
    assert r.success, r.error
    return r


def exhaust_innings(eng: GameEngine, room: Room) -> None:
    """
    Keep bowling identical numbers until the innings is over.
    Uses bat=3, bowl=3 to cause wickets immediately.
    """
    game = room.game
    assert game is not None
    while game.status == GameStatus.CHOOSING_NUMBERS:
        play_ball(eng, room, 3, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# TOSS
# ═══════════════════════════════════════════════════════════════════════════════


class TestToss:
    def test_start_toss_transitions_to_toss(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        r = eng.start_toss(room)
        assert r.success
        assert room.game.status == GameStatus.TOSS

    def test_start_toss_assigns_caller_and_responder(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        game = room.game
        assert game.toss_caller_player_id    in room.players
        assert game.toss_responder_player_id in room.players
        assert game.toss_caller_player_id != game.toss_responder_player_id

    def test_caller_from_team_a_responder_from_team_b(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        game = room.game
        caller_team    = room.players[game.toss_caller_player_id].team_id
        responder_team = room.players[game.toss_responder_player_id].team_id
        assert caller_team    == "team_a"
        assert responder_team == "team_b"

    def test_wrong_player_cannot_call(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller, responder = room.game.toss_caller_player_id, room.game.toss_responder_player_id
        # Responder tries to call — should fail
        r = eng.submit_toss_call(room, responder, TossCall.ODD, 3)
        assert not r.success

    def test_wrong_player_cannot_respond(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller, responder = room.game.toss_caller_player_id, room.game.toss_responder_player_id
        eng.submit_toss_call(room, caller, TossCall.ODD, 3)
        # Caller tries to respond — should fail
        r = eng.submit_toss_response(room, caller, 2)
        assert not r.success

    def test_toss_number_out_of_range_rejected(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller = room.game.toss_caller_player_id
        r = eng.submit_toss_call(room, caller, TossCall.ODD, 11)
        assert not r.success

    def test_even_call_wins_on_even_sum(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller, responder = room.game.toss_caller_player_id, room.game.toss_responder_player_id
        eng.submit_toss_call(room, caller, TossCall.EVEN, 4)
        r = eng.submit_toss_response(room, responder, 2)  # sum=6 even
        assert r.success
        assert room.game.toss_winner_team_id == room.players[caller].team_id

    def test_odd_call_wins_on_odd_sum(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller, responder = room.game.toss_caller_player_id, room.game.toss_responder_player_id
        eng.submit_toss_call(room, caller, TossCall.ODD, 3)
        r = eng.submit_toss_response(room, responder, 2)  # sum=5 odd
        assert r.success
        assert room.game.toss_winner_team_id == room.players[caller].team_id

    def test_toss_decision_locked_after_response(self):
        """Cannot respond twice."""
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        eng.start_toss(room)
        caller, responder = room.game.toss_caller_player_id, room.game.toss_responder_player_id
        eng.submit_toss_call(room, caller, TossCall.EVEN, 4)
        eng.submit_toss_response(room, responder, 2)
        # State is now TOSS_DECISION — cannot respond again
        r = eng.submit_toss_response(room, responder, 2)
        assert not r.success


# ═══════════════════════════════════════════════════════════════════════════════
# TOSS DECISION
# ═══════════════════════════════════════════════════════════════════════════════


class TestTossDecision:
    def test_winner_can_decide_bat(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        batting_team = do_toss_and_decide(eng, room, TossDecision.BAT)
        game = room.game
        assert game.innings is not None
        assert game.innings.batting_team_id == batting_team
        assert game.status == GameStatus.CHOOSING_NUMBERS

    def test_winner_can_decide_bowl(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BOWL)
        game = room.game
        assert game.innings is not None
        # Winner chose bowl, so they are the bowling team
        assert game.innings.bowling_team_id == game.toss_winner_team_id

    def test_non_winner_cannot_decide(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        caller, responder = start_toss_get_players(eng, room)
        game = room.game
        eng.submit_toss_call(room, caller, TossCall.EVEN, 4)
        eng.submit_toss_response(room, responder, 2)
        # losing team player tries to decide
        loser_team = _other_team(game.toss_winner_team_id)
        loser_player = next(
            pid for pid, p in room.players.items()
            if p.team_id == loser_team
        )
        r = eng.submit_toss_decision(room, loser_player, TossDecision.BAT)
        assert not r.success

    def test_decision_locked_after_acceptance(self):
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        # State is now CHOOSING_NUMBERS — toss decision rejected
        game = room.game
        winner_player = next(
            pid for pid, p in room.players.items()
            if p.team_id == game.toss_winner_team_id
        )
        r = eng.submit_toss_decision(room, winner_player, TossDecision.BOWL)
        assert not r.success


# ═══════════════════════════════════════════════════════════════════════════════
# INNINGS SETUP
# ═══════════════════════════════════════════════════════════════════════════════


class TestInningsSetup:
    def test_batting_order_populated(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        game   = room.game
        innings = game.innings
        assert len(innings.batting_order) == 1
        batting_team = innings.batting_team_id
        assert innings.batting_order[0] in room.teams[batting_team].player_ids

    def test_total_wickets_equal_to_players_without_extra(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings = room.game.innings
        assert innings.total_wickets_available == 1

    def test_total_wickets_plus_one_with_extra(self):
        eng  = make_engine()
        # team_a bats first with extra_wicket
        room, _, _, _, _ = make_1v1_room(extra_a=True)
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings = room.game.innings
        # The winning team gets extra: check if batting team has extra
        batting_team = innings.batting_team_id
        if room.teams[batting_team].extra_wicket_available:
            assert innings.total_wickets_available == 2
        else:
            assert innings.total_wickets_available == 1

    def test_2v2_batting_order_has_all_players(self):
        eng      = make_engine()
        room, ta_players, tb_players = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings = room.game.innings
        bat_team = innings.batting_team_id
        expected = set(room.teams[bat_team].player_ids)
        assert set(innings.batting_order) == expected
        assert innings.total_wickets_available == 2


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════════


class TestScoring:
    def test_normal_ball_adds_runs(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        r = play_ball(eng, room, 5, 3)
        assert r.success
        assert room.game.innings.score == 5

    def test_multiple_balls_accumulate(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 4, 2)
        play_ball(eng, room, 6, 1)
        play_ball(eng, room, 3, 5)
        assert room.game.innings.score == 13

    def test_wicket_ball_adds_no_runs(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 3, 3)  # wicket
        # Innings should end (1v1, 1 wicket = all out)
        assert room.game.status == GameStatus.INNINGS_BREAK
        assert room.game.innings.score == 0

    def test_zero_rule_scores_bowler_number(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 0, 7)  # batsman=0, bowler=7 → +7
        assert room.game.innings.score == 7

    def test_zero_rule_all_values_1_to_10(self):
        for bowl_num in range(1, 11):
            eng  = make_engine()
            room, _, _, _, _ = make_1v1_room()
            do_toss_and_decide(eng, room, TossDecision.BAT)
            play_ball(eng, room, 0, bowl_num)
            assert room.game.innings.score == bowl_num, f"bowl={bowl_num}"

    def test_batsman_zero_bowler_zero_is_wicket(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 0, 0)
        assert room.game.status == GameStatus.INNINGS_BREAK
        assert room.game.innings.score == 0

    def test_normal_batting_with_bowler_zero(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 8, 0)   # batsman=8, bowler=0 → +8
        assert room.game.innings.score == 8

    def test_batsman_stats_updated(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        play_ball(eng, room, 6, 3)
        assert room.players[bat_id].batting_stats.runs_scored == 6
        assert room.players[bat_id].batting_stats.balls_faced == 1

    def test_bowler_stats_updated(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bowl_id = room.game.innings.current_bowler_id
        play_ball(eng, room, 4, 2)
        assert room.players[bowl_id].bowling_stats.balls_bowled    == 1
        assert room.players[bowl_id].bowling_stats.runs_conceded   == 4

    def test_bowler_wicket_stat_recorded(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bowl_id = room.game.innings.current_bowler_id
        play_ball(eng, room, 5, 5)  # wicket
        assert room.players[bowl_id].bowling_stats.wickets_taken == 1


# ═══════════════════════════════════════════════════════════════════════════════
# UNLIMITED BALLS
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnlimitedBalls:
    def test_game_does_not_end_after_many_non_wicket_balls(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        game = room.game
        # Play 1 000 scoring balls (bat=1, bowl=2 → +1 each)
        for _ in range(1_000):
            assert game.status == GameStatus.CHOOSING_NUMBERS
            play_ball(eng, room, 1, 2)
        assert game.innings.score == 1_000
        assert game.status == GameStatus.CHOOSING_NUMBERS

    def test_total_balls_counter_increments_correctly(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        for i in range(50):
            play_ball(eng, room, 2, 3)
        assert room.game.innings.total_balls == 50


# ═══════════════════════════════════════════════════════════════════════════════
# WICKETS AND BATTING ROTATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestBattingRotation:
    def test_1v1_wicket_ends_innings(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 4, 4)  # wicket
        assert room.game.status == GameStatus.INNINGS_BREAK

    def test_2v2_first_wicket_advances_batsman(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        game    = room.game
        innings = game.innings
        first_batsman  = innings.current_batsman_id
        play_ball(eng, room, 5, 5)  # wicket
        assert game.status == GameStatus.CHOOSING_NUMBERS
        second_batsman = innings.current_batsman_id
        assert second_batsman != first_batsman

    def test_2v2_second_wicket_ends_innings(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        game = room.game
        play_ball(eng, room, 5, 5)  # wicket 1 → advances
        assert game.status == GameStatus.CHOOSING_NUMBERS
        play_ball(eng, room, 5, 5)  # wicket 2 → innings over
        assert game.status == GameStatus.INNINGS_BREAK

    def test_dismissed_player_cannot_bat_again_normally(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        game    = room.game
        innings = game.innings
        first   = innings.current_batsman_id
        play_ball(eng, room, 5, 5)  # dismiss first
        assert innings.dismissed.get(first) is True
        # The new current batsman must be different
        assert innings.current_batsman_id != first

    def test_batting_order_respected_in_2v2(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings = room.game.innings
        expected_order = innings.batting_order[:]
        first  = innings.current_batsman_id
        play_ball(eng, room, 5, 5)  # dismiss first
        second = innings.current_batsman_id
        assert first  == expected_order[0]
        assert second == expected_order[1]

    def test_runs_scored_by_correct_batsman(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings    = room.game.innings
        first_bat  = innings.current_batsman_id
        # Score 7 runs for the first batsman
        play_ball(eng, room, 7, 3)
        assert room.players[first_bat].batting_stats.runs_scored == 7
        # Dismiss first batsman; second batsman steps in
        play_ball(eng, room, 5, 5)   # wicket
        second_bat = innings.current_batsman_id
        assert second_bat != first_bat
        assert room.players[second_bat].batting_stats.runs_scored == 0


# ═══════════════════════════════════════════════════════════════════════════════
# DUPLICATE / STALE ACTION REJECTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestActionValidation:
    def test_batsman_cannot_submit_twice(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        eng.submit_number(room, bat_id, 3)
        r = eng.submit_number(room, bat_id, 5)  # second submission
        assert not r.success

    def test_non_participant_cannot_submit(self):
        """A player who is neither current batsman nor bowler is rejected."""
        eng       = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings   = room.game.innings
        bat_id    = innings.current_batsman_id
        bowl_id   = innings.current_bowler_id
        # Find a player who is neither
        other = next(
            pid for pid in room.players
            if pid != bat_id and pid != bowl_id
        )
        r = eng.submit_number(room, other, 5)
        assert not r.success

    def test_wrong_state_rejects_number(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        eng.start_toss(room)
        # State is TOSS — submit_number must fail
        r = eng.submit_number(room, "p1", 3)
        assert not r.success


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRA WICKET
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtraWicket:
    def _setup_extra_wicket_vote(
        self, batting_team_has_extra: bool = True
    ) -> tuple[GameEngine, Room, str, str]:
        """
        1v1 room where the batting team has an extra wicket.
        Dismiss the only batsman to trigger the vote.
        Returns (eng, room, batsman_id, bowler_id).
        """
        eng = make_engine()
        if batting_team_has_extra:
            room, p1, p2, ta, tb = make_1v1_room(extra_a=True)
        else:
            room, p1, p2, ta, tb = make_1v1_room(extra_b=True)

        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id  = room.game.innings.current_batsman_id
        bowl_id = room.game.innings.current_bowler_id

        # Dismiss the batsman
        r = play_ball(eng, room, 3, 3)
        # Should now be in EXTRA_WICKET_VOTE
        assert room.game.status == GameStatus.EXTRA_WICKET_VOTE, (
            f"Expected EXTRA_WICKET_VOTE, got {room.game.status}"
        )
        return eng, room, bat_id, bowl_id

    def test_extra_wicket_vote_triggers_after_dismissal(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        assert room.game.extra_wicket_vote is not None

    def test_extra_wicket_vote_has_correct_candidates(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        vote = room.game.extra_wicket_vote
        # The dismissed batsman is the candidate
        assert bat_id in vote.candidates

    def test_vote_selects_unique_winner(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        voter = room.game.extra_wicket_vote.eligible_voters[0]
        r = eng.submit_extra_wicket_vote(room, voter, bat_id)
        assert r.success
        assert room.game.status == GameStatus.CHOOSING_NUMBERS
        innings = room.game.innings
        assert innings.current_batsman_id == bat_id

    def test_non_voter_cannot_vote(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        # bowl_id is on the bowling team — cannot vote
        r = eng.submit_extra_wicket_vote(room, bowl_id, bat_id)
        assert not r.success

    def test_double_vote_rejected(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        voter = room.game.extra_wicket_vote.eligible_voters[0]
        eng.submit_extra_wicket_vote(room, voter, bat_id)
        # Voter already voted; result was decided → state is CHOOSING_NUMBERS
        # Attempting again should fail (wrong state)
        r = eng.submit_extra_wicket_vote(room, voter, bat_id)
        assert not r.success

    def test_invalid_candidate_rejected(self):
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        voter = room.game.extra_wicket_vote.eligible_voters[0]
        r = eng.submit_extra_wicket_vote(room, voter, "nonexistent_player")
        assert not r.success

    def test_no_extra_wicket_vote_without_extra_wicket_flag(self):
        """Without extra_wicket_available, dismissal ends innings directly."""
        eng  = make_engine()
        room, p1, p2, ta, tb = make_1v1_room()  # no extra wicket
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 3, 3)  # wicket
        assert room.game.status == GameStatus.INNINGS_BREAK
        assert room.game.extra_wicket_vote is None

    def test_extra_wicket_innings_ends_after_extra_wicket_dismissed(self):
        """After the extra batsman is also dismissed, innings must end."""
        eng, room, bat_id, bowl_id = self._setup_extra_wicket_vote()
        voter = room.game.extra_wicket_vote.eligible_voters[0]
        eng.submit_extra_wicket_vote(room, voter, bat_id)
        # Now bat_id is back at the crease for the extra wicket
        play_ball(eng, room, 3, 3)  # dismiss again
        assert room.game.status == GameStatus.INNINGS_BREAK


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRA WICKET VOTING — TIE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtraWicketVoteTie:
    def _three_voter_tie_setup(self) -> tuple[GameEngine, Room, list[str], str]:
        """
        Build a 3v1 room where the batting team (3 players) has an extra wicket.
        All three batsmen get dismissed to trigger voting.
        Returns (eng, room, [voter1, voter2, voter3], bowler_id).
        """
        p = {}
        for pid, name in [("a1","Alice"),("a2","Ana"),("a3","Amy")]:
            player = Player(id=pid, display_name=name)
            player.team_id = "team_a"
            player.ready   = True
            p[pid] = player
        bowl = Player(id="b1", display_name="Bob")
        bowl.team_id = "team_b"
        bowl.ready   = True
        p["b1"] = bowl

        team_a = Team(id="team_a", name="Team 1",
                      player_ids=["a1","a2","a3"],
                      extra_wicket_available=True)
        team_b = Team(id="team_b", name="Team 2", player_ids=["b1"])

        room         = Room(host_id="a1")
        room.players = p
        room.teams   = {"team_a": team_a, "team_b": team_b}
        room.game    = GameState()

        eng = make_engine()
        # Force team_a to win toss and bat
        eng.start_toss(room)
        caller    = room.game.toss_caller_player_id
        responder = room.game.toss_responder_player_id
        # caller is team_a rep; EVEN + (4,2) → sum=6 even → caller wins
        eng.submit_toss_call(room, caller, TossCall.EVEN, 4)
        eng.submit_toss_response(room, responder, 2)
        winner_team = room.game.toss_winner_team_id
        decider = next(
            pid for pid, player in room.players.items()
            if player.team_id == winner_team
        )
        eng.submit_toss_decision(room, decider, TossDecision.BAT)

        # Dismiss all 3 batsmen
        for _ in range(3):
            assert room.game.status == GameStatus.CHOOSING_NUMBERS
            play_ball(eng, room, 5, 5)

        assert room.game.status == GameStatus.EXTRA_WICKET_VOTE
        return eng, room, ["a1","a2","a3"], "b1"

    def test_three_way_tie_starts_new_round(self):
        eng, room, voters, bowler = self._three_voter_tie_setup()
        vote = room.game.extra_wicket_vote

        # Each voter votes for a different candidate → 3-way tie
        assert len(vote.candidates) == 3
        eng.submit_extra_wicket_vote(room, voters[0], vote.candidates[0])
        eng.submit_extra_wicket_vote(room, voters[1], vote.candidates[1])
        eng.submit_extra_wicket_vote(room, voters[2], vote.candidates[2])

        # Still in EXTRA_WICKET_VOTE with round 2
        assert room.game.status == GameStatus.EXTRA_WICKET_VOTE
        assert room.game.extra_wicket_vote.round == 2

    def test_tie_then_resolved_in_round_2(self):
        eng, room, voters, bowler = self._three_voter_tie_setup()
        vote = room.game.extra_wicket_vote
        candidates = list(vote.candidates)

        # Round 1: a1→c0, a2→c1, a3→c2 → 3-way tie
        eng.submit_extra_wicket_vote(room, voters[0], candidates[0])
        eng.submit_extra_wicket_vote(room, voters[1], candidates[1])
        eng.submit_extra_wicket_vote(room, voters[2], candidates[2])

        # Round 2 starts — candidates are the tied ones (all 3)
        assert room.game.extra_wicket_vote.round == 2
        r2_candidates = list(room.game.extra_wicket_vote.candidates)

        # All three voters now unanimously pick r2_candidates[0]
        eng.submit_extra_wicket_vote(room, voters[0], r2_candidates[0])
        eng.submit_extra_wicket_vote(room, voters[1], r2_candidates[0])
        eng.submit_extra_wicket_vote(room, voters[2], r2_candidates[0])

        # Unique winner — play resumes
        assert room.game.status == GameStatus.CHOOSING_NUMBERS
        assert room.game.innings.current_batsman_id == r2_candidates[0]

    def test_tie_never_randomly_resolved(self):
        """
        After a tie, round count must increment (not silently pick a winner).
        We assert round increments with each tied vote to prove no auto-resolution.
        """
        eng, room, voters, bowler = self._three_voter_tie_setup()

        for expected_round in range(1, 4):
            vote = room.game.extra_wicket_vote
            assert vote.round == expected_round
            if len(vote.candidates) < len(voters):
                break  # fewer candidates than voters → can't tie; end loop
            # Spread votes evenly to force another tie
            for i, voter in enumerate(voters):
                if voter not in vote.eligible_voters:
                    continue
                candidate = vote.candidates[i % len(vote.candidates)]
                eng.submit_extra_wicket_vote(room, voter, candidate)
            # If still in vote, check round incremented
            if room.game.status == GameStatus.EXTRA_WICKET_VOTE:
                assert room.game.extra_wicket_vote.round == expected_round + 1


# ═══════════════════════════════════════════════════════════════════════════════
# BOWLER SWITCHING
# ═══════════════════════════════════════════════════════════════════════════════


class TestBowlerSwitch:
    def _get_bowling_team_second_player(
        self, room: Room, current_bowler: str
    ) -> str:
        innings = room.game.innings
        bowling_team_players = [
            pid for pid in room.teams[innings.bowling_team_id].player_ids
            if pid != current_bowler
        ]
        return bowling_team_players[0] if bowling_team_players else ""

    def test_request_switch_transitions_to_bowler_switch(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings  = room.game.innings
        bowl_id  = innings.current_bowler_id
        new_bowl = self._get_bowling_team_second_player(room, bowl_id)

        r = eng.request_bowler_switch(room, new_bowl, new_bowl)
        assert r.success
        assert room.game.status == GameStatus.BOWLER_SWITCH

    def test_current_bowler_can_accept(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings  = room.game.innings
        bowl_id  = innings.current_bowler_id
        new_bowl = self._get_bowling_team_second_player(room, bowl_id)

        eng.request_bowler_switch(room, new_bowl, new_bowl)
        r = eng.respond_bowler_switch(room, bowl_id, accept=True)
        assert r.success
        assert room.game.innings.current_bowler_id == new_bowl
        assert room.game.status == GameStatus.CHOOSING_NUMBERS

    def test_current_bowler_can_decline(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings  = room.game.innings
        bowl_id  = innings.current_bowler_id
        new_bowl = self._get_bowling_team_second_player(room, bowl_id)

        eng.request_bowler_switch(room, new_bowl, new_bowl)
        r = eng.respond_bowler_switch(room, bowl_id, accept=False)
        assert r.success
        assert room.game.innings.current_bowler_id == bowl_id  # unchanged
        assert room.game.status == GameStatus.CHOOSING_NUMBERS

    def test_non_current_bowler_cannot_respond(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings  = room.game.innings
        bowl_id  = innings.current_bowler_id
        new_bowl = self._get_bowling_team_second_player(room, bowl_id)

        eng.request_bowler_switch(room, new_bowl, new_bowl)
        r = eng.respond_bowler_switch(room, new_bowl, accept=True)
        assert not r.success

    def test_batting_team_cannot_request_switch(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        innings  = room.game.innings
        bat_id   = innings.current_batsman_id
        r = eng.request_bowler_switch(room, bat_id, bat_id)
        assert not r.success

    def test_current_bowler_cannot_switch_to_self(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bowl_id = room.game.innings.current_bowler_id
        r = eng.request_bowler_switch(room, bowl_id, bowl_id)
        assert not r.success

    def test_switch_only_allowed_in_choosing_numbers(self):
        eng  = make_engine()
        room, ta, tb = make_2v2_room()
        eng.start_toss(room)   # state = TOSS, not CHOOSING_NUMBERS
        r = eng.request_bowler_switch(room, "b1", "b1")
        assert not r.success

    def test_bowler_can_bowl_indefinitely_without_switch(self):
        eng      = make_engine()
        room, ta, tb = make_2v2_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bowl_id = room.game.innings.current_bowler_id
        for _ in range(20):
            play_ball(eng, room, 3, 4)
            assert room.game.innings.current_bowler_id == bowl_id


# ═══════════════════════════════════════════════════════════════════════════════
# FIRST INNINGS END
# ═══════════════════════════════════════════════════════════════════════════════


class TestFirstInnings:
    def test_innings_break_after_all_out(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        # Score some runs then get out
        play_ball(eng, room, 7, 2)   # +7
        play_ball(eng, room, 3, 3)   # wicket
        assert room.game.status == GameStatus.INNINGS_BREAK

    def test_target_is_first_innings_score_plus_one(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 10, 5)  # +10
        play_ball(eng, room, 5, 4)   # +5
        play_ball(eng, room, 3, 3)   # wicket → innings over
        assert room.game.target == 16   # 15 + 1

    def test_history_records_first_innings(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 5, 2)
        play_ball(eng, room, 5, 5)   # wicket
        history = room.game.innings_history
        assert len(history) == 1
        assert history[0].innings_number == 1
        assert history[0].score == 5
        assert history[0].completed is True

    def test_first_innings_score_frozen_at_innings_break(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 8, 3)
        play_ball(eng, room, 4, 4)   # wicket
        frozen = room.game.innings_history[0].score
        assert frozen == 8


# ═══════════════════════════════════════════════════════════════════════════════
# SECOND INNINGS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecondInnings:
    def _end_first_innings(
        self, score: int = 20
    ) -> tuple[GameEngine, Room, str, str]:
        """
        Score exactly `score` runs in the first innings then get out.
        Uses only valid numbers (0-10).
        Returns (eng, room, first_batting_team, first_bowling_team).
        """
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        first_bat  = room.game.innings.batting_team_id
        first_bowl = room.game.innings.bowling_team_id

        remaining = score
        # Score in chunks of up to 10 using bat=chunk, bowl=0 (normal rule)
        while remaining > 0:
            chunk = min(remaining, 10)
            play_ball(eng, room, chunk, 0)   # bat=chunk, bowl=0 → +chunk (normal)
            remaining -= chunk

        play_ball(eng, room, 3, 3)   # wicket → innings over
        return eng, room, first_bat, first_bowl

    def test_start_second_innings_swaps_roles(self):
        eng, room, first_bat, first_bowl = self._end_first_innings()
        r = eng.start_second_innings(room)
        assert r.success
        innings = room.game.innings
        assert innings.batting_team_id  == first_bowl
        assert innings.bowling_team_id  == first_bat

    def test_second_innings_resets_score(self):
        eng, room, _, _ = self._end_first_innings(score=5)
        eng.start_second_innings(room)
        assert room.game.innings.score == 0

    def test_second_innings_resets_wickets(self):
        eng, room, _, _ = self._end_first_innings()
        eng.start_second_innings(room)
        assert room.game.innings.wickets == 0

    def test_second_innings_resets_ball_counter(self):
        eng, room, _, _ = self._end_first_innings()
        eng.start_second_innings(room)
        assert room.game.innings.total_balls == 0

    def test_second_innings_batting_order_rebuilt(self):
        eng, room, first_bat, first_bowl = self._end_first_innings()
        eng.start_second_innings(room)
        innings = room.game.innings
        expected = room.teams[first_bowl].player_ids
        assert innings.batting_order == expected

    def test_innings_number_is_2(self):
        eng, room, _, _ = self._end_first_innings()
        eng.start_second_innings(room)
        assert room.game.innings_number == 2

    def test_state_after_start_is_choosing_numbers(self):
        eng, room, _, _ = self._end_first_innings()
        eng.start_second_innings(room)
        assert room.game.status == GameStatus.CHOOSING_NUMBERS

    def test_cannot_start_second_innings_in_wrong_state(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)  # state = CHOOSING_NUMBERS
        r = eng.start_second_innings(room)
        assert not r.success


# ═══════════════════════════════════════════════════════════════════════════════
# TARGET AND WINNING
# ═══════════════════════════════════════════════════════════════════════════════


class TestTargetAndWinning:
    def _setup_second_innings(
        self, first_score: int
    ) -> tuple[GameEngine, Room]:
        """Score first_score in 1st innings (valid numbers only), then start 2nd innings."""
        eng, room, _, _ = TestSecondInnings()._end_first_innings(score=first_score)
        eng.start_second_innings(room)
        return eng, room

    def test_chasing_team_wins_on_reaching_target(self):
        eng, room = self._setup_second_innings(first_score=10)
        # Target = 11; score 11 with bat=0, bowl=10 + 1 more
        play_ball(eng, room, 0, 10)   # +10
        assert room.game.status == GameStatus.CHOOSING_NUMBERS  # not done yet
        play_ball(eng, room, 1, 2)    # +1 → score=11 >= target=11
        assert room.game.status == GameStatus.GAME_OVER
        assert room.game.final_result is not None
        assert not room.game.final_result.is_tie

    def test_chasing_team_wins_on_exceeding_target(self):
        eng, room = self._setup_second_innings(first_score=5)
        # Target = 6; score 10 in one shot
        play_ball(eng, room, 10, 3)  # +10 → score=10 >= target=6
        assert room.game.status == GameStatus.GAME_OVER

    def test_target_checked_on_every_ball(self):
        """Target must be checked after every scoring ball, not just at wickets."""
        eng, room = self._setup_second_innings(first_score=3)
        # Target = 4
        play_ball(eng, room, 1, 2)  # +1 → 1 < 4
        play_ball(eng, room, 1, 2)  # +1 → 2 < 4
        play_ball(eng, room, 1, 2)  # +1 → 3 < 4
        assert room.game.status == GameStatus.CHOOSING_NUMBERS
        play_ball(eng, room, 1, 2)  # +1 → 4 >= 4
        assert room.game.status == GameStatus.GAME_OVER

    def test_defending_team_wins_if_all_wickets_fall(self):
        eng, room = self._setup_second_innings(first_score=50)
        # Target = 51; score a few runs then get out
        play_ball(eng, room, 5, 3)   # +5 (5 < 51)
        play_ball(eng, room, 3, 3)   # wicket → innings over, score=5 < 51
        assert room.game.status == GameStatus.GAME_OVER
        result = room.game.final_result
        assert result is not None
        defending = room.game.innings_history[0].batting_team_id
        assert result.winner_team_id == defending

    def test_tie_when_scores_equal(self):
        """
        Tie: second innings score == first innings score AND second innings wickets fall.
        First innings scores 5 → target = 6.
        Second innings scores 5 then wicket → 5 < 6 → defending wins, not a tie.

        True tie: both innings complete with equal scores AND the chaser
        exhausts all wickets at exactly first_score (score == first_score < target).
        By our rules: is_tie when inn1.score == inn2.score.
        """
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        # First innings: score 5 → target = 6
        play_ball(eng, room, 5, 3)    # +5
        play_ball(eng, room, 3, 3)    # wicket
        eng.start_second_innings(room)
        # Second innings: score exactly 5 then wicket → 5 == inn1.score → TIE
        play_ball(eng, room, 5, 3)    # +5
        play_ball(eng, room, 3, 3)    # wicket → game over
        assert room.game.status == GameStatus.GAME_OVER
        result = room.game.final_result
        assert result is not None
        # inn2.score=5 == inn1.score=5 → tie
        assert result.is_tie is True

    def test_no_further_balls_after_game_over(self):
        eng, room = self._setup_second_innings(first_score=2)
        play_ball(eng, room, 3, 2)   # +3 → score=3 >= target=3
        assert room.game.status == GameStatus.GAME_OVER
        r = eng.submit_number(room, room.game.innings.current_batsman_id, 5)
        assert not r.success


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatistics:
    def test_batting_runs_accumulate_across_balls(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        play_ball(eng, room, 5, 3)
        play_ball(eng, room, 7, 2)
        play_ball(eng, room, 3, 1)
        assert room.players[bat_id].batting_stats.runs_scored == 15
        assert room.players[bat_id].batting_stats.balls_faced == 3

    def test_batting_stats_not_reset_at_innings_break(self):
        """Stats should persist across the innings break for career totals."""
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        play_ball(eng, room, 8, 2)
        play_ball(eng, room, 4, 4)  # wicket
        # Stats frozen at innings break
        assert room.players[bat_id].batting_stats.runs_scored == 8

    def test_highest_score_updated_at_innings_end(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        play_ball(eng, room, 6, 2)
        play_ball(eng, room, 3, 3)  # wicket → innings ends → close_innings called
        assert room.players[bat_id].batting_stats.highest_score == 6

    def test_bowling_economy_correct(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bowl_id = room.game.innings.current_bowler_id
        # 6 balls conceding 6 runs each → 36 runs in 1 over → economy = 36.0
        for _ in range(6):
            play_ball(eng, room, 6, 3)
        stats = room.players[bowl_id].bowling_stats
        assert stats.balls_bowled   == 6
        assert stats.runs_conceded  == 36
        # economy = runs_conceded / (balls_bowled / 6) = 36 / 1 = 36.0
        assert stats.economy == 36.0

    def test_innings_count_increments_per_innings(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        bat_id = room.game.innings.current_batsman_id
        play_ball(eng, room, 5, 5)   # wicket → innings ends
        # innings_count should be 1
        assert room.players[bat_id].batting_stats.innings_count == 1

    def test_team_score_in_history_correct(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 10, 3)
        play_ball(eng, room, 8, 5)
        play_ball(eng, room, 3, 3)  # wicket
        h = room.game.innings_history[0]
        assert h.score   == 18
        assert h.wickets == 1

    def test_second_innings_score_in_history(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        # First innings: score 20 → target = 21
        play_ball(eng, room, 10, 3)
        play_ball(eng, room, 10, 4)
        play_ball(eng, room, 3, 3)   # wicket → first innings done, score=20
        eng.start_second_innings(room)
        # Second innings: score 9 (< target 21), then wicket
        play_ball(eng, room, 9, 2)   # +9 → score=9 < 21
        play_ball(eng, room, 4, 4)   # wicket → game over
        assert room.game.status == GameStatus.GAME_OVER
        h2 = room.game.innings_history[1]
        assert h2.innings_number == 2
        assert h2.score          == 9


# ═══════════════════════════════════════════════════════════════════════════════
# STATE MACHINE INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestStateMachineInvariants:
    def test_invalid_transition_raises(self):
        """Engine must not allow skipping states."""
        from app.game.engine import _transition, GameStatus
        game = GameState()
        with pytest.raises(ValueError):
            _transition(game, GameStatus.GAME_OVER)  # LOBBY → GAME_OVER invalid

    def test_game_over_is_terminal(self):
        eng, room = TestTargetAndWinning()._setup_second_innings(3)
        # target = 4; score 4 to end the game
        play_ball(eng, room, 4, 3)   # +4 → score=4 >= target=4 → GAME_OVER
        assert room.game.status == GameStatus.GAME_OVER
        # Any further action must fail
        r = eng.start_second_innings(room)
        assert not r.success

    def test_cannot_start_toss_twice(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        eng.start_toss(room)
        r = eng.start_toss(room)  # already started
        assert not r.success

    def test_first_and_second_innings_history_preserved(self):
        eng  = make_engine()
        room, _, _, _, _ = make_1v1_room()
        do_toss_and_decide(eng, room, TossDecision.BAT)
        play_ball(eng, room, 5, 3)
        play_ball(eng, room, 3, 3)  # wicket → 1st innings done
        eng.start_second_innings(room)
        play_ball(eng, room, 2, 2)  # wicket → 2nd innings done
        assert len(room.game.innings_history) == 2
        assert room.game.innings_history[0].innings_number == 1
        assert room.game.innings_history[1].innings_number == 2
