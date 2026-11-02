"""HTTP contract tests: status codes and JSON shapes the frontend relies on."""

from datetime import timedelta

from sqlalchemy import update

from app.models import SyncRun
from app.providers.base import ProviderError
from app.services.sync import utcnow


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_leagues_returns_the_six_seeded(client):
    response = await client.get("/api/leagues")
    assert response.status_code == 200
    body = response.json()
    assert [lg["code"] for lg in body] == ["PL", "PD", "BL1", "SA", "FL1", "CL"]
    assert set(body[0]) == {"code", "name", "country", "emblem_url"}


async def test_unknown_code_is_404(client, stub_provider):
    assert (await client.post("/api/leagues/XX/sync")).status_code == 404
    assert (await client.get("/api/leagues/XX/standings")).status_code == 404
    assert stub_provider.calls == []


async def test_standings_before_any_sync_is_empty(client):
    response = await client.get("/api/leagues/PL/standings")
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == [] and body["season"] is None and body["fetched_at"] is None


async def test_sync_then_cache_then_stored(client, stub_provider, pl_result):
    live = await client.post("/api/leagues/PL/sync")
    assert live.status_code == 200
    body = live.json()
    assert set(body) == {"league", "season", "fetched_at", "source", "rows"}
    assert body["source"] == "live" and len(body["rows"]) == len(pl_result.rows)
    assert set(body["rows"][0]) == {
        "position", "team_id", "team_name", "team_crest", "played", "won", "draw", "lost",
        "goals_for", "goals_against", "goal_difference", "points", "form",
    }

    cached = await client.post("/api/leagues/pl/sync")  # lower-case code accepted
    assert cached.json()["source"] == "cache"
    assert cached.json()["rows"] == body["rows"]

    stored = await client.get("/api/leagues/PL/standings")
    assert stored.json()["rows"] == body["rows"]

    assert stub_provider.calls == ["PL"]


async def test_provider_failure_is_502_with_last_known(client, stub_provider, session_factory):
    stub_provider.error = ProviderError("rate limit hit", status_code=429)
    first = await client.post("/api/leagues/PL/sync")
    assert first.status_code == 502
    assert first.json() == {"detail": "rate limit hit", "last_known": None}

    stub_provider.error = None
    await client.post("/api/leagues/PL/sync")
    async with session_factory() as s:  # make the cache stale
        await s.execute(update(SyncRun).values(finished_at=utcnow() - timedelta(minutes=11)))
        await s.commit()

    stub_provider.error = ProviderError("football-data.org returned HTTP 503", status_code=503)
    second = await client.post("/api/leagues/PL/sync")
    assert second.status_code == 502
    assert second.json()["detail"] == "football-data.org returned HTTP 503"
    assert len(second.json()["last_known"]["rows"]) > 0


async def test_cors_allows_vite_dev_origin(client):
    response = await client.options(
        "/api/leagues/PL/sync",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
