"""Sync service against real Postgres, with the provider stubbed."""

import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models import League, Standing, SyncRun
from app.providers.base import ProviderError
from app.services.sync import LeagueNotFound, SyncFailed, sync_league, utcnow
from tests.conftest import StubProvider

TTL = 600


async def runs(session) -> list[tuple[str, int | None]]:
    rows = await session.execute(select(SyncRun.status, SyncRun.rows_written).order_by(SyncRun.id))
    return [tuple(r) for r in rows]


async def standing_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Standing))


async def age_last_success(session, minutes: int) -> None:
    """Pretend the last successful sync happened `minutes` ago."""
    await session.execute(
        update(SyncRun).where(SyncRun.status == "success")
        .values(finished_at=utcnow() - timedelta(minutes=minutes))
    )
    await session.commit()


async def test_first_sync_is_live_and_stores_every_row(session, stub_provider, pl_result):
    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert stub_provider.calls == ["PL"]
    assert response.source == "live"
    assert response.season == pl_result.season
    assert response.league.code == "PL"
    assert [r.position for r in response.rows] == list(range(1, len(pl_result.rows) + 1))
    assert response.rows[0].team_name == pl_result.rows[0].team_name
    assert response.fetched_at is not None
    assert await standing_count(session) == len(pl_result.rows)
    assert await runs(session) == [("success", len(pl_result.rows))]


async def test_second_sync_within_ttl_skips_provider(session, stub_provider):
    first = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    second = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert stub_provider.calls == ["PL"]  # no second provider call
    assert second.source == "cache"
    assert second.rows == first.rows
    assert second.fetched_at == first.fetched_at
    assert [s for s, _ in await runs(session)] == ["success", "skipped"]


async def test_sync_after_ttl_calls_provider_again(session, stub_provider):
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    await age_last_success(session, minutes=11)

    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert stub_provider.calls == ["PL", "PL"]
    assert response.source == "live"


async def test_upsert_updates_rows_in_place(session, stub_provider, pl_result):
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    ids_before = dict((await session.execute(select(Standing.team_id, Standing.id))).all())

    leader = pl_result.rows[0]
    changed = dataclasses.replace(leader, played=leader.played + 1, won=leader.won + 1, points=leader.points + 3)
    stub_provider.result = dataclasses.replace(pl_result, rows=[changed, *pl_result.rows[1:]])
    await age_last_success(session, minutes=11)

    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert await standing_count(session) == len(pl_result.rows)  # no duplicates
    ids_after = dict((await session.execute(select(Standing.team_id, Standing.id))).all())
    assert ids_after == ids_before  # same rows, updated via ON CONFLICT DO UPDATE
    assert response.rows[0].points == leader.points + 3


async def test_team_missing_from_provider_is_removed(session, stub_provider, pl_result):
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    stub_provider.result = dataclasses.replace(pl_result, rows=pl_result.rows[:-1])
    await age_last_success(session, minutes=11)

    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert len(response.rows) == len(pl_result.rows) - 1
    assert pl_result.rows[-1].team_id not in {r.team_id for r in response.rows}


async def test_seasons_are_stored_separately(session, stub_provider, pl_result):
    stub_provider.result = dataclasses.replace(pl_result, season="2025-2026")
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    stub_provider.result = pl_result
    await age_last_success(session, minutes=11)

    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert await standing_count(session) == 2 * len(pl_result.rows)
    assert response.season == pl_result.season


async def test_provider_failure_records_failed_run(session, pl_result):
    provider = StubProvider(error=ProviderError("rate limit hit", status_code=429))

    with pytest.raises(SyncFailed) as exc_info:
        await sync_league(session, provider, "PL", cache_ttl_seconds=TTL)

    assert exc_info.value.detail == "rate limit hit"
    assert exc_info.value.last_known is None  # nothing stored yet
    failed = await session.scalar(select(SyncRun))
    assert (failed.status, failed.error) == ("failed", "rate limit hit")
    assert failed.finished_at is not None


async def test_provider_failure_returns_last_known_table(session, stub_provider, pl_result):
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    await age_last_success(session, minutes=11)
    stub_provider.error = ProviderError("football-data.org timed out")

    with pytest.raises(SyncFailed) as exc_info:
        await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    last_known = exc_info.value.last_known
    assert last_known is not None and last_known.source == "cache"
    assert len(last_known.rows) == len(pl_result.rows)
    assert await standing_count(session) == len(pl_result.rows)  # stored table untouched


async def test_failed_or_skipped_runs_do_not_count_as_fresh(session, stub_provider):
    stub_provider.error = ProviderError("boom")
    with pytest.raises(SyncFailed):
        await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    stub_provider.error = None
    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert response.source == "live"
    assert len(stub_provider.calls) == 2


async def test_write_failure_rolls_back_everything(session, stub_provider, pl_result):
    broken = dataclasses.replace(pl_result.rows[5], team_name=None)  # violates NOT NULL
    stub_provider.result = dataclasses.replace(pl_result, rows=[*pl_result.rows[:5], broken])

    with pytest.raises(IntegrityError):
        await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    await session.rollback()

    assert await standing_count(session) == 0  # no partial table
    assert "success" not in [s for s, _ in await runs(session)]


async def test_provider_emblem_overwrites_seed(session, stub_provider, pl_result):
    stub_provider.result = dataclasses.replace(pl_result, emblem_url="https://example.test/pl.svg")
    response = await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)

    assert response.league.emblem_url == "https://example.test/pl.svg"
    stored = await session.scalar(select(League.emblem_url).where(League.code == "PL"))
    assert stored == "https://example.test/pl.svg"


async def test_unknown_league_raises(session, stub_provider):
    with pytest.raises(LeagueNotFound):
        await sync_league(session, stub_provider, "XX", cache_ttl_seconds=TTL)
    assert stub_provider.calls == []


async def test_leagues_are_cached_independently(session, stub_provider):
    await sync_league(session, stub_provider, "PL", cache_ttl_seconds=TTL)
    response = await sync_league(session, stub_provider, "BL1", cache_ttl_seconds=TTL)

    assert stub_provider.calls == ["PL", "BL1"]
    assert response.source == "live"
