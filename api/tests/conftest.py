"""Shared fixtures. DB tests run against a real Postgres database named <app db>_test.

Run inside Docker:  docker compose run --rm api pytest
"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import get_session
from app.main import app
from app.providers.base import ProviderError, StandingsProvider, StandingsResult
from app.providers.football_data import map_standings
from app.routers.leagues import get_provider

API_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pl_standings.json"


def _test_db_url() -> URL:
    if explicit := os.environ.get("TEST_DATABASE_URL"):
        url = make_url(explicit)
    else:
        base = make_url(get_settings().database_url)
        url = base.set(database=f"{base.database}_test")
    if not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to run tests against non-test database {url.database!r}")
    return url


TEST_DB_URL = _test_db_url()


async def _ensure_database(url: URL) -> None:
    conn = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port or 5432,
        database="postgres",
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Create the test DB and run the real Alembic migrations (down to base, then up to head)."""
    asyncio.run(_ensure_database(TEST_DB_URL))
    env = {**os.environ, "DATABASE_URL": TEST_DB_URL.render_as_string(hide_password=False)}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, check=True,
            capture_output=True,
        )


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:  # clean slate per test; seeded leagues stay
        await conn.execute(text("TRUNCATE standings, sync_runs RESTART IDENTITY"))
        await conn.execute(text(
            "UPDATE leagues SET emblem_url = 'https://crests.football-data.org/' || code || '.png'"
        ))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture
def pl_result() -> StandingsResult:
    return map_standings(json.loads(FIXTURE_PATH.read_text()))


class StubProvider(StandingsProvider):
    """Stands in for football-data.org in tests. Records every call."""

    name = "stub"

    def __init__(self, result: StandingsResult | None = None, error: ProviderError | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def fetch_standings(self, code: str) -> StandingsResult:
        self.calls.append(code)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.fixture
def stub_provider(pl_result) -> StubProvider:
    return StubProvider(result=pl_result)


@pytest.fixture
async def client(session_factory, stub_provider) -> AsyncIterator[httpx.AsyncClient]:
    async def _test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _test_session
    app.dependency_overrides[get_provider] = lambda: stub_provider
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
