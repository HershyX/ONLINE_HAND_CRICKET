"""
FastAPI application entry point.

No game logic lives here — only HTTP/WebSocket transport.
All domain operations are in services and the engine.

Note on SQLite persistence:
  db.py exists for future match-history features but is NOT initialised on
  startup because SQLAlchemy's async layer requires the `greenlet` package,
  which has no pre-built wheel for Python 3.14. All game state is in-memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import rooms
from app.config import settings
from app.websocket import router as ws_router

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("hand_cricket")

# ─── App instance ─────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    # No lifespan — DB init removed (greenlet unavailable on Python 3.14)
)

# ─── CORS middleware ──────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_effective_cors_origins(),
    allow_origin_regex=settings.get_cors_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Health check ─────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(rooms.router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
