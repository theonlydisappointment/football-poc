from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    emblem_url: Mapped[str | None] = mapped_column(Text)


class Standing(Base):
    """One team's row in one league's table for one season."""

    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint("league_id", "season", "team_id", name="uq_standings_league_season_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    season: Mapped[str] = mapped_column(String(9))
    team_id: Mapped[int]
    team_name: Mapped[str] = mapped_column(Text)
    team_crest: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int]
    played: Mapped[int]
    won: Mapped[int]
    draw: Mapped[int]
    lost: Mapped[int]
    goals_for: Mapped[int]
    goals_against: Mapped[int]
    goal_difference: Mapped[int]
    points: Mapped[int]
    form: Mapped[str | None] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncRun(Base):
    """Audit log: one row per Pull League Data click (success, skipped or failed)."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint("status IN ('success', 'skipped', 'failed')", name="ck_sync_runs_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    status: Mapped[str] = mapped_column(String(10))
    rows_written: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
