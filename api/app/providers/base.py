"""The provider contract. Sync logic depends only on this file, never on a concrete API."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TeamStanding:
    team_id: int
    team_name: str
    team_crest: str | None
    position: int
    played: int
    won: int
    draw: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str | None


@dataclass(frozen=True)
class StandingsResult:
    competition_code: str
    season: str  # e.g. "2026-2027"
    rows: list[TeamStanding]
    emblem_url: str | None = None


class ProviderError(Exception):
    """Anything that stops us getting a usable table: rate limit, 5xx, timeout, bad key, bad payload.

    The message is shown to the user, so it must never contain the API key.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class StandingsProvider(ABC):
    name: str

    @abstractmethod
    async def fetch_standings(self, code: str) -> StandingsResult:
        """Return the current overall league table for a competition code like "PL".

        Raise ProviderError on any failure.
        """

    async def aclose(self) -> None:
        """Release network resources. Called once on app shutdown."""
