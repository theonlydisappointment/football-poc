"""Pydantic models for everything the API returns. These define the JSON contract with the frontend."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LeagueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    country: str | None
    emblem_url: str | None


class StandingRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    team_id: int
    team_name: str
    team_crest: str | None
    played: int
    won: int
    draw: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str | None


class StandingsResponse(BaseModel):
    league: LeagueOut
    season: str | None  # None until the league has been synced at least once
    fetched_at: datetime | None
    source: Literal["live", "cache"]
    rows: list[StandingRow]


class SyncErrorResponse(BaseModel):
    detail: str
    last_known: StandingsResponse | None
