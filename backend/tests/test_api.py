"""
Integration tests for the REST API.
Uses httpx AsyncClient against the live FastAPI app (no network).
"""

import pytest


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "timestamp" in body


class TestCreateRoom:
    async def test_create_room_returns_code_and_player_id(self, client):
        resp = await client.post(
            "/api/rooms",
            json={"display_name": "Alice", "overs_per_innings": 2},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "room_code" in body
        assert "host_player_id" in body
        assert len(body["room_code"]) == 6

    async def test_create_room_default_overs(self, client):
        resp = await client.post("/api/rooms", json={"display_name": "Bob"})
        assert resp.status_code == 201

    async def test_create_room_short_name_rejected(self, client):
        resp = await client.post("/api/rooms", json={"display_name": "A"})
        assert resp.status_code == 422

    async def test_create_room_long_name_rejected(self, client):
        resp = await client.post(
            "/api/rooms", json={"display_name": "A" * 21}
        )
        assert resp.status_code == 422


class TestGetRoom:
    async def test_get_existing_room(self, client):
        # Create first
        create_resp = await client.post(
            "/api/rooms", json={"display_name": "Alice"}
        )
        code = create_resp.json()["room_code"]

        get_resp = await client.get(f"/api/rooms/{code}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["room_code"] == code
        assert body["player_count"] == 1
        assert body["max_players"] == 10

    async def test_get_nonexistent_room_returns_404(self, client):
        resp = await client.get("/api/rooms/XXXXXX")
        assert resp.status_code == 404
