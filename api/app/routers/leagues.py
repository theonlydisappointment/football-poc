"""HTTP layer only: parse the request, call the service, turn exceptions into status codes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import League
from app.providers.base import StandingsProvider
from app.schemas import LeagueOut, StandingsResponse, SyncErrorResponse
from app.services.sync import LeagueNotFound, SyncFailed, get_league, read_table, sync_league

router = APIRouter(prefix="/api/leagues", tags=["leagues"])


def get_provider(request: Request) -> StandingsProvider:
    """The provider instance created once in main.lifespan. Tests override this dependency."""
    return request.app.state.provider


@router.get("", response_model=list[LeagueOut])
async def list_leagues(session: AsyncSession = Depends(get_session)) -> list[League]:
    return list(await session.scalars(select(League).order_by(League.id)))


@router.post(
    "/{code}/sync",
    response_model=StandingsResponse,
    responses={404: {"description": "Unknown league code"}, 502: {"model": SyncErrorResponse}},
)
async def sync(
    code: str,
    session: AsyncSession = Depends(get_session),
    provider: StandingsProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
):
    try:
        return await sync_league(session, provider, code, cache_ttl_seconds=settings.cache_ttl_seconds)
    except LeagueNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown league code '{code}'") from None
    except SyncFailed as exc:
        body = SyncErrorResponse(detail=exc.detail, last_known=exc.last_known)
        return JSONResponse(status_code=502, content=body.model_dump(mode="json"))


@router.get("/{code}/standings", response_model=StandingsResponse)
async def standings(code: str, session: AsyncSession = Depends(get_session)) -> StandingsResponse:
    try:
        league = await get_league(session, code)
    except LeagueNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown league code '{code}'") from None
    return await read_table(session, league, source="cache")
