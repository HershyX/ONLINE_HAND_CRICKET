"""
SQLite persistence layer for completed matches.

Room state and in-progress game state remain purely in-memory (fast, no lock
contention).  When a match ends (GAME_OVER), the final result is persisted
here for historical lookup, leaderboards, and future features.

Uses SQLAlchemy async with aiosqlite.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# ─── SQLAlchemy setup ─────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class MatchRecord(Base):
    """Persisted completed match."""

    __tablename__ = "matches"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    room_code: str = Column(String(6), index=True, nullable=False)
    played_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Teams
    team_a_name: str = Column(String(50), nullable=False)
    team_b_name: str = Column(String(50), nullable=False)

    # Scores
    team_a_score: int = Column(Integer, default=0, nullable=False)
    team_a_wickets: int = Column(Integer, default=0, nullable=False)
    team_a_balls: int = Column(Integer, default=0, nullable=False)

    team_b_score: int = Column(Integer, default=0, nullable=False)
    team_b_wickets: int = Column(Integer, default=0, nullable=False)
    team_b_balls: int = Column(Integer, default=0, nullable=False)

    # Result
    winner_team_id: str = Column(String(10), nullable=True)  # None = tie
    is_tie: bool = Column(Boolean, default=False, nullable=False)
    margin: str = Column(String(50), nullable=True)  # e.g. "3 wickets", "25 runs"

    # MVP
    mvp_player_id: str = Column(String(36), nullable=True)
    mvp_player_name: str = Column(String(20), nullable=True)

    # Player count
    player_count: int = Column(Integer, default=0, nullable=False)

    # Metadata
    innings_summary: str = Column(Text, nullable=True)  # JSON-serialized innings_history


# ─── Database lifecycle ───────────────────────────────────────────────────────


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()


# ─── Persistence helper ───────────────────────────────────────────────────────


async def persist_match(
    room_code: str,
    team_a_name: str,
    team_b_name: str,
    team_a_score: int,
    team_a_wickets: int,
    team_a_balls: int,
    team_b_score: int,
    team_b_wickets: int,
    team_b_balls: int,
    winner_team_id: str | None,
    is_tie: bool,
    margin: str | None,
    mvp_player_id: str | None,
    mvp_player_name: str | None,
    player_count: int,
    innings_summary: str | None = None,
) -> None:
    """Write a completed match to the database."""
    try:
        async with async_session() as session:
            record = MatchRecord(
                room_code=room_code,
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                team_a_score=team_a_score,
                team_a_wickets=team_a_wickets,
                team_a_balls=team_a_balls,
                team_b_score=team_b_score,
                team_b_wickets=team_b_wickets,
                team_b_balls=team_b_balls,
                winner_team_id=winner_team_id,
                is_tie=is_tie,
                margin=margin,
                mvp_player_id=mvp_player_id,
                mvp_player_name=mvp_player_name,
                player_count=player_count,
                innings_summary=innings_summary,
            )
            session.add(record)
            await session.commit()
            logger.info("Persisted match: room=%s", room_code)
    except Exception:
        logger.exception("Failed to persist match for room %s", room_code)
