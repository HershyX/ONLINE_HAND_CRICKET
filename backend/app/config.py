"""
Application configuration — loaded from environment variables / .env file.
All game-critical values live here so they're easy to override in tests
or different deployment environments.

Environment:
  - "development" (default): debug=True, reload=True, permissive CORS
  - "production":  debug=False, reload=False, strict CORS, structured logging
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "production"] = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    debug: bool = True

    # CORS — comma-separated in .env, parsed as list[str]
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # Frontend origin for CORS in production (e.g. "https://handcricket.example.com")
    frontend_origin: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./hand_cricket.db"

    # App metadata
    app_version: str = "0.1.0"
    app_name: str = "Hand Cricket API"

    # Room limits
    max_players_per_room: int = 10
    room_code_length: int = 6

    # Game defaults — 0 means unlimited overs (game ends on wicket only)
    default_overs_per_innings: int = 0
    max_overs_per_innings: int = 50
    balls_per_over: int = 6

    # In-memory room TTL (seconds) — rooms with no activity are garbage-collected
    room_ttl_seconds: int = 3600  # 1 hour

    # Logging
    log_level: str = "info"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def get_effective_cors_origins(self) -> list[str]:
        """Return CORS origins, including the explicit frontend_origin for prod."""
        origins = list(self.cors_origins)
        if self.frontend_origin:
            origins.append(self.frontend_origin)
        return origins


# Singleton — imported everywhere as `settings`
settings = Settings()

# ─── Environment-driven defaults ─────────────────────────────────────────────
# Override reload/debug/log_level when running in production.
if settings.is_production:
    settings.reload = False
    settings.debug = False
    settings.log_level = os.getenv("LOG_LEVEL", "warning")
