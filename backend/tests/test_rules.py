"""
Unit tests for rules.py — zero I/O, zero FastAPI.

Updated for the new rule set:
  - Numbers 0-10 (not 0-6)
  - Zero special rule: batsman=0, bowler!=0 → runs = bowler_number
  - is_innings_complete uses InningsState (no over limit)
  - calculate_result uses innings_history team IDs
"""

import pytest

from app.game.rules import (
    calculate_result,
    is_innings_complete,
    is_target_reached,
    resolve_ball,
    resolve_toss,
)
from app.models.domain import (
    GameState,
    InningsHistory,
    InningsState,
    Player,
    Room,
    TossCall,
)


# ─── Toss ─────────────────────────────────────────────────────────────────────


class TestResolveToss:
    def test_odd_call_wins_on_odd_sum(self):
        assert resolve_toss("p1", "p2", TossCall.ODD, 3, 2) == "p1"   # 5 odd

    def test_odd_call_loses_on_even_sum(self):
        assert resolve_toss("p1", "p2", TossCall.ODD, 3, 3) == "p2"   # 6 even

    def test_even_call_wins_on_even_sum(self):
        assert resolve_toss("p1", "p2", TossCall.EVEN, 4, 2) == "p1"  # 6 even

    def test_even_call_wins_on_zero_sum(self):
        assert resolve_toss("p1", "p2", TossCall.EVEN, 0, 0) == "p1"  # 0 even

    def test_even_call_loses_on_odd_sum(self):
        assert resolve_toss("p1", "p2", TossCall.EVEN, 1, 2) == "p2"  # 3 odd

    def test_large_numbers(self):
        # 10 + 10 = 20 (even)
        assert resolve_toss("p1", "p2", TossCall.EVEN, 10, 10) == "p1"
        # 10 + 9 = 19 (odd)
        assert resolve_toss("p1", "p2", TossCall.ODD, 10, 9) == "p1"


# ─── Ball resolution — core rules ─────────────────────────────────────────────


class TestResolveBallCore:
    def test_matching_numbers_is_wicket(self):
        for n in range(0, 11):
            r = resolve_ball(n, n, 1)
            assert r.is_wicket is True,  f"n={n} should be out"
            assert r.runs == 0,          f"n={n} wicket should score 0"

    def test_different_numbers_score_batsman_number(self):
        # Normal case: batsman != bowler, batsman != 0
        for bat in range(1, 11):
            for bowl in range(0, 11):
                if bat == bowl:
                    continue
                r = resolve_ball(bat, bowl, 1)
                assert r.runs == bat,        f"bat={bat} bowl={bowl}"
                assert r.is_wicket is False, f"bat={bat} bowl={bowl}"

    def test_ball_number_stored(self):
        r = resolve_ball(5, 3, 42)
        assert r.ball_number == 42

    def test_invalid_batsman_above_10(self):
        with pytest.raises(ValueError):
            resolve_ball(11, 3, 1)

    def test_invalid_batsman_below_0(self):
        with pytest.raises(ValueError):
            resolve_ball(-1, 3, 1)

    def test_invalid_bowler_above_10(self):
        with pytest.raises(ValueError):
            resolve_ball(5, 11, 1)

    def test_invalid_bowler_below_0(self):
        with pytest.raises(ValueError):
            resolve_ball(5, -1, 1)

    def test_boundary_10_scores_10(self):
        r = resolve_ball(10, 9, 1)
        assert r.runs == 10
        assert r.is_wicket is False

    def test_boundary_0_vs_10_scores_bowler(self):
        r = resolve_ball(0, 10, 1)
        assert r.runs == 10
        assert r.is_wicket is False


# ─── Zero special rule — exhaustive ───────────────────────────────────────────


class TestZeroSpecialRule:
    """
    Batsman = 0, Bowler = 0   → OUT  (matching)
    Batsman = 0, Bowler = N   → runs = N  (zero special)
    Batsman = N, Bowler = 0   → runs = N  (normal)
    """

    def test_zero_vs_zero_is_out(self):
        r = resolve_ball(0, 0, 1)
        assert r.is_wicket is True
        assert r.runs == 0

    def test_zero_bat_vs_1_scores_1(self):
        r = resolve_ball(0, 1, 1)
        assert r.runs == 1
        assert r.is_wicket is False

    def test_zero_bat_vs_2_scores_2(self):
        r = resolve_ball(0, 2, 1)
        assert r.runs == 2

    def test_zero_bat_vs_3_scores_3(self):
        r = resolve_ball(0, 3, 1)
        assert r.runs == 3

    def test_zero_bat_vs_4_scores_4(self):
        r = resolve_ball(0, 4, 1)
        assert r.runs == 4

    def test_zero_bat_vs_5_scores_5(self):
        r = resolve_ball(0, 5, 1)
        assert r.runs == 5

    def test_zero_bat_vs_6_scores_6(self):
        r = resolve_ball(0, 6, 1)
        assert r.runs == 6

    def test_zero_bat_vs_7_scores_7(self):
        r = resolve_ball(0, 7, 1)
        assert r.runs == 7

    def test_zero_bat_vs_8_scores_8(self):
        r = resolve_ball(0, 8, 1)
        assert r.runs == 8

    def test_zero_bat_vs_9_scores_9(self):
        r = resolve_ball(0, 9, 1)
        assert r.runs == 9

    def test_zero_bat_vs_10_scores_10(self):
        r = resolve_ball(0, 10, 1)
        assert r.runs == 10

    def test_1_bat_vs_zero_bowl_scores_1(self):
        r = resolve_ball(1, 0, 1)
        assert r.runs == 1
        assert r.is_wicket is False

    def test_5_bat_vs_zero_bowl_scores_5(self):
        r = resolve_ball(5, 0, 1)
        assert r.runs == 5

    def test_10_bat_vs_zero_bowl_scores_10(self):
        r = resolve_ball(10, 0, 1)
        assert r.runs == 10

    def test_zero_bat_not_out_for_any_nonzero_bowler(self):
        for bowl in range(1, 11):
            r = resolve_ball(0, bowl, 1)
            assert r.is_wicket is False, f"bowler={bowl}"


# ─── Innings completion ───────────────────────────────────────────────────────


class TestInningsComplete:
    def _innings(self, **kwargs) -> InningsState:
        defaults = dict(
            batting_team_id="team_a",
            bowling_team_id="team_b",
            batting_order=["p1"],
            dismissed={"p1": False},
            current_batsman_idx=0,
            total_wickets_available=1,
        )
        defaults.update(kwargs)
        return InningsState(**defaults)

    def test_not_complete_with_wickets_remaining(self):
        innings = self._innings(wickets=0, total_wickets_available=1)
        assert is_innings_complete(innings) is False

    def test_complete_when_all_wickets_gone(self):
        innings = self._innings(wickets=1, total_wickets_available=1)
        assert is_innings_complete(innings) is True

    def test_two_players_one_out(self):
        innings = self._innings(
            batting_order=["p1", "p2"],
            dismissed={"p1": True, "p2": False},
            total_wickets_available=2,
            wickets=1,
        )
        assert is_innings_complete(innings) is False

    def test_two_players_both_out(self):
        innings = self._innings(
            batting_order=["p1", "p2"],
            dismissed={"p1": True, "p2": True},
            total_wickets_available=2,
            wickets=2,
        )
        assert is_innings_complete(innings) is True

    def test_never_ends_on_balls_alone(self):
        """The innings must NOT end just because many balls have been played."""
        innings = self._innings(
            total_balls=10_000,
            wickets=0,
            total_wickets_available=1,
        )
        assert is_innings_complete(innings) is False

    def test_extra_wicket_extends_innings(self):
        # 2 normal players out, but extra wicket not yet used
        innings = self._innings(
            batting_order=["p1", "p2"],
            dismissed={"p1": True, "p2": True},
            total_wickets_available=3,  # 2 normal + 1 extra
            wickets=2,
            extra_wicket_used=False,
        )
        assert is_innings_complete(innings) is False

    def test_extra_wicket_used_completes_innings(self):
        innings = self._innings(
            batting_order=["p1", "p2", "p1"],   # p1 re-bats as extra
            dismissed={"p1": True, "p2": True},
            total_wickets_available=3,
            wickets=2,
            extra_wicket_used=True,
        )
        # wickets_used = 2 normal + 1 extra = 3 = total_wickets_available
        assert is_innings_complete(innings) is True


class TestTargetReached:
    def _innings(self, score: int) -> InningsState:
        return InningsState(
            batting_team_id="team_b",
            bowling_team_id="team_a",
            batting_order=["p1"],
            dismissed={"p1": False},
            total_wickets_available=1,
            score=score,
        )

    def test_target_reached_exactly(self):
        assert is_target_reached(self._innings(50), 50) is True

    def test_target_exceeded(self):
        assert is_target_reached(self._innings(51), 50) is True

    def test_target_not_reached(self):
        assert is_target_reached(self._innings(49), 50) is False

    def test_zero_target(self):
        assert is_target_reached(self._innings(0), 0) is True


# ─── Result calculation ───────────────────────────────────────────────────────


class TestCalculateResult:
    def _room_and_game(
        self, score1: int, score2: int
    ) -> tuple[Room, GameState]:
        p1 = Player(id="p1", display_name="Alice")
        p2 = Player(id="p2", display_name="Bob")
        p1.team_id = "team_a"
        p2.team_id = "team_b"
        room = Room(host_id="p1")
        room.players = {"p1": p1, "p2": p2}

        inn1 = InningsHistory(
            innings_number=1,
            batting_team_id="team_a",
            bowling_team_id="team_b",
            score=score1,
            completed=True,
        )
        inn2 = InningsHistory(
            innings_number=2,
            batting_team_id="team_b",
            bowling_team_id="team_a",
            score=score2,
            completed=True,
        )
        game = GameState(innings_history=[inn1, inn2])

        # Provide a live innings so wickets_remaining is calculable
        game.innings = InningsState(
            batting_team_id="team_b",
            bowling_team_id="team_a",
            batting_order=["p2"],
            dismissed={"p2": False},
            total_wickets_available=1,
            score=score2,
            wickets=0,
        )
        room.game = game
        return room, game

    def test_first_team_defends(self):
        room, game = self._room_and_game(50, 30)
        r = calculate_result(room, game)
        assert r.winner_team_id == "team_a"
        assert r.margin_runs == 20
        assert r.is_tie is False

    def test_second_team_chases(self):
        room, game = self._room_and_game(30, 50)
        r = calculate_result(room, game)
        assert r.winner_team_id == "team_b"
        assert r.is_tie is False

    def test_tie(self):
        room, game = self._room_and_game(40, 40)
        r = calculate_result(room, game)
        assert r.is_tie is True
        assert r.winner_team_id is None

    def test_raises_without_two_innings(self):
        room = Room(host_id="p1")
        game = GameState()
        with pytest.raises(ValueError):
            calculate_result(room, game)
