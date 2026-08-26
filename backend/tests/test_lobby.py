"""
Tests for the new lobby system:
  - team-size validation
  - extra-wicket rule
  - display name update
  - team switching
  - start-match pre-conditions
  - join guards (game started, full)
"""

import pytest

from app.models.domain import (
    compute_extra_wicket,
    validate_team_sizes,
)
from app.services.room_service import (
    GameAlreadyStartedError,
    GameError,
    RoomFullError,
    create_room,
    join_room,
    set_player_ready,
    start_match,
    switch_team,
    update_display_name,
)
from app.game.state import registry


# ─── Helper ───────────────────────────────────────────────────────────────────


async def make_two_player_room() -> tuple[str, str, str]:
    """Returns (room_code, host_id, guest_id)."""
    room, host_id = await create_room("Alice")
    room2, guest_id = await join_room(room.room_code, "Bob")
    return room.room_code, host_id, guest_id


# ─── Team size validation ─────────────────────────────────────────────────────


class TestValidateTeamSizes:
    def test_equal_teams_ok(self):
        assert validate_team_sizes(2, 2) is None
        assert validate_team_sizes(1, 1) is None
        assert validate_team_sizes(5, 5) is None

    def test_one_diff_ok(self):
        assert validate_team_sizes(2, 3) is None
        assert validate_team_sizes(3, 2) is None
        assert validate_team_sizes(4, 5) is None

    def test_two_diff_invalid(self):
        assert validate_team_sizes(1, 3) is not None
        assert validate_team_sizes(2, 4) is not None
        assert validate_team_sizes(2, 5) is not None

    def test_empty_team_invalid(self):
        assert validate_team_sizes(0, 3) is not None
        assert validate_team_sizes(3, 0) is not None
        assert validate_team_sizes(0, 0) is not None


# ─── Extra wicket ─────────────────────────────────────────────────────────────


class TestComputeExtraWicket:
    def test_equal_no_extra(self):
        assert compute_extra_wicket(2, 2) == (False, False)

    def test_team_a_smaller_gets_extra(self):
        a, b = compute_extra_wicket(2, 3)
        assert a is True
        assert b is False

    def test_team_b_smaller_gets_extra(self):
        a, b = compute_extra_wicket(3, 2)
        assert a is False
        assert b is True


# ─── Update display name ──────────────────────────────────────────────────────


class TestUpdateDisplayName:
    async def test_name_changes(self):
        room, host_id = await create_room("OriginalName")
        updated = await update_display_name(room.room_code, host_id, "NewName")
        assert updated.players[host_id].display_name == "NewName"

    async def test_short_name_rejected(self):
        room, host_id = await create_room("Alice")
        with pytest.raises(GameError, match="2"):
            await update_display_name(room.room_code, host_id, "A")

    async def test_long_name_rejected(self):
        room, host_id = await create_room("Alice")
        with pytest.raises(GameError):
            await update_display_name(room.room_code, host_id, "A" * 21)

    async def test_name_trimmed(self):
        room, host_id = await create_room("Alice")
        updated = await update_display_name(room.room_code, host_id, "  Bob  ")
        assert updated.players[host_id].display_name == "Bob"


# ─── Team switching ───────────────────────────────────────────────────────────


class TestSwitchTeam:
    async def test_player_switches_team(self):
        room, host_id = await create_room("Alice")
        assert room.players[host_id].team_id == "team_a"
        updated = await switch_team(room.room_code, host_id, "team_b")
        assert updated.players[host_id].team_id == "team_b"
        assert host_id in updated.teams["team_b"].player_ids
        assert host_id not in updated.teams["team_a"].player_ids

    async def test_switch_resets_ready(self):
        room, host_id = await create_room("Alice")
        await set_player_ready(room.room_code, host_id, True)
        updated = await switch_team(room.room_code, host_id, "team_b")
        assert updated.players[host_id].ready is False

    async def test_switch_to_same_team_noop(self):
        room, host_id = await create_room("Alice")
        await set_player_ready(room.room_code, host_id, True)
        updated = await switch_team(room.room_code, host_id, "team_a")
        # ready state should be unchanged since it was a no-op
        assert updated.players[host_id].ready is True

    async def test_invalid_team_rejected(self):
        room, host_id = await create_room("Alice")
        with pytest.raises(GameError):
            await switch_team(room.room_code, host_id, "team_c")  # type: ignore


# ─── Start match ──────────────────────────────────────────────────────────────


class TestStartMatch:
    async def test_start_requires_host(self):
        room_code, host_id, guest_id = await make_two_player_room()
        # Make both ready first
        await set_player_ready(room_code, host_id, True)
        await set_player_ready(room_code, guest_id, True)
        # Guest tries to start — should fail
        with pytest.raises(GameError, match="host"):
            await start_match(room_code, guest_id)

    async def test_start_requires_all_ready(self):
        room_code, host_id, guest_id = await make_two_player_room()
        # Only host ready
        await set_player_ready(room_code, host_id, True)
        with pytest.raises(GameError):
            await start_match(room_code, host_id)

    async def test_start_requires_valid_teams(self):
        room, host_id = await create_room("Alice")
        room2, guest_id = await join_room(room.room_code, "Bob")
        # Move both to team_a — team_b will be empty
        await switch_team(room.room_code, guest_id, "team_a")
        await set_player_ready(room.room_code, host_id, True)
        await set_player_ready(room.room_code, guest_id, True)
        with pytest.raises(GameError):
            await start_match(room.room_code, host_id)

    async def test_start_succeeds_with_valid_state(self):
        room_code, host_id, guest_id = await make_two_player_room()
        await set_player_ready(room_code, host_id, True)
        await set_player_ready(room_code, guest_id, True)
        updated_room = await start_match(room_code, host_id)
        assert updated_room.room_status.value == "IN_GAME"
        assert updated_room.game is not None
        assert updated_room.game.status.value == "TOSS"

    async def test_team_locked_after_start(self):
        room_code, host_id, guest_id = await make_two_player_room()
        await set_player_ready(room_code, host_id, True)
        await set_player_ready(room_code, guest_id, True)
        await start_match(room_code, host_id)
        with pytest.raises(GameError, match="locked"):
            await switch_team(room_code, host_id, "team_b")


# ─── Join guards ─────────────────────────────────────────────────────────────


class TestJoinGuards:
    async def test_join_started_game_rejected(self):
        room_code, host_id, guest_id = await make_two_player_room()
        await set_player_ready(room_code, host_id, True)
        await set_player_ready(room_code, guest_id, True)
        await start_match(room_code, host_id)
        with pytest.raises(GameAlreadyStartedError):
            await join_room(room_code, "Newcomer")

    async def test_reconnect_works_after_start(self):
        room_code, host_id, guest_id = await make_two_player_room()
        await set_player_ready(room_code, host_id, True)
        await set_player_ready(room_code, guest_id, True)
        await start_match(room_code, host_id)
        # Existing player reconnects using their UUID
        room, pid = await join_room(room_code, "Alice", player_id=host_id)
        assert pid == host_id
        assert room.players[host_id].connected is True
