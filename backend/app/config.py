"""
Application configuration — loaded from environment variables / .env file.

Environment modes
─────────────────
  development (default)  debug=True, permissive CORS (all localhost ports)
  production             debug=False, strict CORS (only listed origins)

Required env vars for Render deployment
────────────────────────────────────────
  ENVIRONMENT=production
  FRONTEND_ORIGIN=https://your-app.vercel.app
  # Optional: comma-separated extra origins (preview deploys, custom domains)
  # EXTRA_ORIGINS=https://hand-cricket-git-main-yourname.vercel.app
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

    # ── Runtime environment ───────────────────────────────────────────────────
    environment: Literal["development", "production"] = "development"

    # ── Server ────────────────────────────────────────────────────────────────
    host:   str  = "0.0.0.0"
    port:   int  = 8000
    reload: bool = True
    debug:  bool = True

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Always-allowed origins (localhost variants for dev)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # Primary production frontend URL (set on Render)
    # Example: https://hand-cricket.vercel.app
    frontend_origin: str = ""

    # Extra comma-separated origins (Vercel preview URLs, custom domains)
    # Example: https://hand-cricket-git-main-user.vercel.app,https://custom.domain.com
    extra_origins: str = ""

    # ── Database (unused at runtime — greenlet unavailable on Py 3.14) ────────
    database_url: str = "sqlite+aiosqlite:///./hand_cricket.db"

    # ── App metadata ──────────────────────────────────────────────────────────
    app_version: str = "0.1.0"
    app_name:    str = "Hand Cricket API"

    # ── Game defaults ─────────────────────────────────────────────────────────
    max_players_per_room:    int = 10
    room_code_length:        int = 6
    default_overs_per_innings: int = 0
    max_overs_per_innings:   int = 50
    balls_per_over:          int = 6
    room_ttl_seconds:        int = 3600

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "info"

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def get_effective_cors_origins(self) -> list[str]:
        """Return the full list of allowed CORS origins."""
        origins = list(self.cors_origins)
        if self.frontend_origin:
            origins.append(self.frontend_origin.rstrip("/"))
        if self.extra_origins:
            for o in self.extra_origins.split(","):
                o = o.strip().rstrip("/")
                if o:
                    origins.append(o)
        return origins

    def get_cors_regex(self) -> str | None:
        """
        In dev: allow any localhost port (covers Vite bumping to 5174 etc.).
        In prod: also allow all *.vercel.app preview URLs so PR previews work.
        """
        if self.is_production:
            return r"https://[a-zA-Z0-9\-]+\.vercel\.app"
        return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


settings = Settings()

# Override mutable defaults when running in production
if settings.is_production:
    settings.reload = False
    settings.debug  = False
    settings.log_level = os.getenv("LOG_LEVEL", "warning")
