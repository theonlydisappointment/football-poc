"""football-data.org v4 adapter: HTTP call + mapping into our provider-neutral dataclasses."""

import logging
from datetime import date
from typing import Any

import httpx

from app.providers.base import ProviderError, StandingsProvider, StandingsResult, TeamStanding

logger = logging.getLogger(__name__)


class FootballDataProvider(StandingsProvider):
    name = "football-data.org"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.football-data.org/v4",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Keys pasted into dashboards often carry a trailing newline or space, which makes the
        # header invalid (httpx raises LocalProtocolError before sending anything).
        api_key = api_key.strip()
        self._has_key = bool(api_key)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Auth-Token": api_key},
            timeout=timeout,
            transport=transport,  # tests can inject httpx.MockTransport
        )

    async def fetch_standings(self, code: str) -> StandingsResult:
        if not self._has_key:
            raise ProviderError("FOOTBALL_DATA_API_KEY is not set on the API server")

        logger.info("provider=%s fetching standings code=%s", self.name, code)
        try:
            response = await self._client.get(f"/competitions/{code}/standings")
        except httpx.TimeoutException:
            raise ProviderError(f"{self.name} timed out") from None
        except httpx.LocalProtocolError:
            raise ProviderError(
                f"Could not build the request to {self.name}: "
                "check FOOTBALL_DATA_API_KEY for stray characters"
            ) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach {self.name} ({type(exc).__name__})") from None

        if response.status_code == 429:
            raise ProviderError(
                f"{self.name} rate limit hit (10 requests/minute on the free tier). Try again shortly.",
                status_code=429,
            )
        if response.status_code in (401, 403):
            raise ProviderError(
                f"{self.name} rejected the request ({response.status_code}): "
                "check FOOTBALL_DATA_API_KEY and that your plan includes this competition",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} returned HTTP {response.status_code}", status_code=response.status_code
            )

        try:
            return map_standings(response.json())
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            raise ProviderError(f"{self.name} returned an unexpected response: {exc}") from None

    async def aclose(self) -> None:
        await self._client.aclose()


def season_label(season: dict[str, Any]) -> str:
    """{"startDate": "2026-08-15", "endDate": "2027-05-23"} -> "2026-2027" (or "2026" for calendar-year leagues)."""
    start = date.fromisoformat(season["startDate"]).year
    end = date.fromisoformat(season["endDate"]).year
    return str(start) if start == end else f"{start}-{end}"


def map_standings(payload: dict[str, Any]) -> StandingsResult:
    """Pure function: football-data.org JSON -> StandingsResult. Raises ValueError on a bad shape."""
    try:
        total = next((s for s in payload["standings"] if s.get("type") == "TOTAL"), None)
        if total is None:
            raise ValueError("no standings entry with type TOTAL")

        rows = []
        for entry in total["table"]:
            team = entry["team"]
            form = entry.get("form")
            rows.append(
                TeamStanding(
                    team_id=int(team["id"]),
                    team_name=team.get("shortName") or team["name"],
                    team_crest=team.get("crest"),
                    position=int(entry["position"]),
                    played=int(entry["playedGames"]),
                    won=int(entry["won"]),
                    draw=int(entry["draw"]),
                    lost=int(entry["lost"]),
                    goals_for=int(entry["goalsFor"]),
                    goals_against=int(entry["goalsAgainst"]),
                    goal_difference=int(entry["goalDifference"]),
                    points=int(entry["points"]),
                    form=form[:20] if form else None,
                )
            )

        competition = payload["competition"]
        return StandingsResult(
            competition_code=competition["code"],
            season=season_label(payload["season"]),
            rows=rows,
            emblem_url=competition.get("emblem"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing or malformed field {exc}") from None
