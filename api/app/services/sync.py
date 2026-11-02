"""Sync logic: freshness check -> provider call -> transactional upsert -> read back from Postgres.

Talks to providers only through the StandingsProvider interface.
"""

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import League, Standing, SyncRun
from app.providers.base import ProviderError, StandingsProvider, StandingsResult
from app.schemas import LeagueOut, StandingRow, StandingsResponse

logger = logging.getLogger(__name__)

# Columns refreshed on conflict. The conflict key (league_id, season, team_id) never changes.
UPDATABLE_COLUMNS = (
    "team_name", "team_crest", "position", "played", "won", "draw", "lost",
    "goals_for", "goals_against", "goal_difference", "points", "form",
)


class LeagueNotFound(Exception):
    pass


class SyncFailed(Exception):
    def __init__(self, detail: str, last_known: StandingsResponse | None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.last_known = last_known


def utcnow() -> datetime:
    return datetime.now(UTC)


async def get_league(session: AsyncSession, code: str) -> League:
    league = await session.scalar(select(League).where(League.code == code.upper()))
    if league is None:
        raise LeagueNotFound(code)
    return league


async def has_fresh_success(session: AsyncSession, league_id: int, ttl_seconds: int) -> bool:
    """True if the latest successful sync for this league finished less than ttl_seconds ago."""
    last_success = await session.scalar(
        select(func.max(SyncRun.finished_at)).where(
            SyncRun.league_id == league_id, SyncRun.status == "success"
        )
    )
    return last_success is not None and utcnow() - last_success < timedelta(seconds=ttl_seconds)


async def upsert_standings(session: AsyncSession, league: League, result: StandingsResult) -> int:
    """Write the provider table into Postgres. Caller commits, so this is one transaction."""
    if result.rows:
        values = [
            {"league_id": league.id, "season": result.season, **asdict(row)} for row in result.rows
        ]
        stmt = pg_insert(Standing).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["league_id", "season", "team_id"],
            set_={col: stmt.excluded[col] for col in UPDATABLE_COLUMNS} | {"fetched_at": func.now()},
        )
        await session.execute(stmt)

    # Keep the stored table an exact mirror: drop teams the provider no longer lists this season.
    await session.execute(
        delete(Standing).where(
            Standing.league_id == league.id,
            Standing.season == result.season,
            Standing.team_id.not_in([r.team_id for r in result.rows]),
        )
    )

    # Self-heal the seeded emblem URL from the provider (flushed by the caller's commit).
    if result.emblem_url:
        league.emblem_url = result.emblem_url

    return len(result.rows)


async def read_table(
    session: AsyncSession,
    league: League,
    source: Literal["live", "cache"] = "cache",
    season: str | None = None,
) -> StandingsResponse:
    """Load the stored table for a league (latest season by default), ordered by position."""
    if season is None:
        season = await session.scalar(
            select(Standing.season)
            .where(Standing.league_id == league.id)
            .order_by(Standing.fetched_at.desc(), Standing.season.desc())
            .limit(1)
        )

    rows: list[Standing] = []
    if season is not None:
        rows = list(
            await session.scalars(
                select(Standing)
                .where(Standing.league_id == league.id, Standing.season == season)
                .order_by(Standing.position)
            )
        )

    return StandingsResponse(
        league=LeagueOut.model_validate(league),
        season=season,
        fetched_at=max((r.fetched_at for r in rows), default=None),
        source=source,
        rows=[StandingRow.model_validate(r) for r in rows],
    )


async def sync_league(
    session: AsyncSession, provider: StandingsProvider, code: str, *, cache_ttl_seconds: int
) -> StandingsResponse:
    """The whole Pull League Data flow. Returns the table as stored in Postgres."""
    league = await get_league(session, code)
    started_at = utcnow()

    # 1. Fresh enough? Serve from Postgres and don't spend a provider request.
    if await has_fresh_success(session, league.id, cache_ttl_seconds):
        session.add(
            SyncRun(league_id=league.id, status="skipped", rows_written=0,
                    started_at=started_at, finished_at=utcnow())
        )
        await session.commit()
        logger.info("sync league=%s status=skipped (fresh within %ss)", league.code, cache_ttl_seconds)
        return await read_table(session, league, source="cache")

    # End the read transaction so no DB connection is held open during the HTTP call.
    await session.commit()

    # 2. Ask the provider.
    try:
        result = await provider.fetch_standings(league.code)
    except ProviderError as exc:
        session.add(
            SyncRun(league_id=league.id, status="failed", error=str(exc),
                    started_at=started_at, finished_at=utcnow())
        )
        await session.commit()
        logger.warning("sync league=%s status=failed error=%s", league.code, exc)
        raise SyncFailed(str(exc), last_known=await _last_known(session, league)) from exc

    # 3. Upsert rows + record success in ONE transaction: both land, or neither does.
    rows_written = await upsert_standings(session, league, result)
    session.add(
        SyncRun(league_id=league.id, status="success", rows_written=rows_written,
                started_at=started_at, finished_at=utcnow())
    )
    await session.commit()
    logger.info("sync league=%s status=success rows=%s season=%s", league.code, rows_written, result.season)

    # 4. Read back what Postgres now holds.
    return await read_table(session, league, source="live", season=result.season)


async def _last_known(session: AsyncSession, league: League) -> StandingsResponse | None:
    table = await read_table(session, league, source="cache")
    return table if table.rows else None
