"""Unit tests for the football-data.org adapter: JSON mapping and HTTP error translation. No DB needed."""

import copy
import json
import re
from pathlib import Path

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.football_data import FootballDataProvider, map_standings, season_label

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "pl_standings.json").read_text())


# ---------------------------------------------------------------- map_standings


def test_maps_every_row_of_the_total_table():
    result = map_standings(FIXTURE)
    total = next(s for s in FIXTURE["standings"] if s["type"] == "TOTAL")

    assert result.competition_code == "PL"
    assert len(result.rows) == len(total["table"]) > 0
    assert [r.position for r in result.rows] == list(range(1, len(result.rows) + 1))


def test_maps_field_names_from_camel_case():
    raw = next(s for s in FIXTURE["standings"] if s["type"] == "TOTAL")["table"][0]
    row = map_standings(FIXTURE).rows[0]

    assert row.team_id == raw["team"]["id"]
    assert row.team_name == (raw["team"].get("shortName") or raw["team"]["name"])
    assert row.team_crest == raw["team"]["crest"]
    assert row.played == raw["playedGames"]
    assert (row.won, row.draw, row.lost) == (raw["won"], raw["draw"], raw["lost"])
    assert (row.goals_for, row.goals_against) == (raw["goalsFor"], raw["goalsAgainst"])
    assert row.goal_difference == raw["goalDifference"]
    assert row.points == raw["points"]
    assert row.form == raw["form"]


def test_rows_are_internally_consistent():
    for row in map_standings(FIXTURE).rows:
        assert row.won + row.draw + row.lost == row.played, row.team_name
        assert row.goals_for - row.goals_against == row.goal_difference, row.team_name


def test_season_label_comes_from_season_dates():
    assert re.fullmatch(r"\d{4}-\d{4}", map_standings(FIXTURE).season)
    assert season_label({"startDate": "2026-08-22", "endDate": "2027-05-30"}) == "2026-2027"
    assert season_label({"startDate": "2026-04-01", "endDate": "2026-12-06"}) == "2026"


def test_picks_total_even_when_it_is_not_first():
    payload = copy.deepcopy(FIXTURE)
    payload["standings"].reverse()  # HOME/AWAY now come before TOTAL
    total = next(s for s in FIXTURE["standings"] if s["type"] == "TOTAL")

    rows = map_standings(payload).rows
    assert [r.points for r in rows] == [e["points"] for e in total["table"]]


def test_null_form_and_missing_short_name():
    payload = copy.deepcopy(FIXTURE)
    entry = next(s for s in payload["standings"] if s["type"] == "TOTAL")["table"][0]
    entry["form"] = None
    del entry["team"]["shortName"]

    row = map_standings(payload).rows[0]
    assert row.form is None
    assert row.team_name == entry["team"]["name"]


def test_missing_total_table_is_an_error():
    payload = copy.deepcopy(FIXTURE)
    payload["standings"] = [s for s in payload["standings"] if s["type"] != "TOTAL"]
    with pytest.raises(ValueError, match="TOTAL"):
        map_standings(payload)


def test_malformed_payload_is_an_error():
    with pytest.raises(ValueError):
        map_standings({"unexpected": True})


# ------------------------------------------------- FootballDataProvider (HTTP layer)


def provider_with(handler) -> FootballDataProvider:
    return FootballDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))


async def test_sends_auth_header_and_maps_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("X-Auth-Token")
        return httpx.Response(200, json=FIXTURE)

    result = await provider_with(handler).fetch_standings("PL")
    assert seen == {"path": "/v4/competitions/PL/standings", "token": "test-key"}
    assert len(result.rows) > 0


@pytest.mark.parametrize(
    ("status", "message"),
    [(429, "rate limit"), (403, "rejected"), (500, "HTTP 500"), (503, "HTTP 503")],
)
async def test_http_errors_become_provider_errors(status, message):
    provider = provider_with(lambda request: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(ProviderError, match=message) as exc_info:
        await provider.fetch_standings("PL")
    assert exc_info.value.status_code == status


async def test_timeout_becomes_provider_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        await provider_with(handler).fetch_standings("PL")


@pytest.mark.parametrize("raw_key", ["test-key\n", " test-key", "test-key \r\n"])
async def test_whitespace_around_key_is_stripped(raw_key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-Auth-Token")
        return httpx.Response(200, json=FIXTURE)

    provider = FootballDataProvider(api_key=raw_key, transport=httpx.MockTransport(handler))
    await provider.fetch_standings("PL")
    assert seen["token"] == "test-key"


async def test_invalid_header_points_at_the_key():
    def handler(request):
        raise httpx.LocalProtocolError("Illegal header value")

    with pytest.raises(ProviderError, match="FOOTBALL_DATA_API_KEY"):
        await provider_with(handler).fetch_standings("PL")


async def test_missing_key_fails_without_calling_the_api():
    calls = []
    provider = FootballDataProvider(
        api_key="", transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200))
    )
    with pytest.raises(ProviderError, match="FOOTBALL_DATA_API_KEY"):
        await provider.fetch_standings("PL")
    assert calls == []


async def test_error_messages_never_contain_the_key():
    provider = FootballDataProvider(
        api_key="super-secret-key", transport=httpx.MockTransport(lambda r: httpx.Response(403))
    )
    with pytest.raises(ProviderError) as exc_info:
        await provider.fetch_standings("PL")
    assert "super-secret-key" not in str(exc_info.value)
