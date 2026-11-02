import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import engine, get_session
from app.providers.football_data import FootballDataProvider
from app.routers import leagues

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = settings.football_data_api_key.get_secret_value()
    if not api_key:
        logger.warning("FOOTBALL_DATA_API_KEY is not set: syncs will fail with 502 until it is")
    # One shared HTTP client (connection pooling) for the app's lifetime.
    app.state.provider = FootballDataProvider(
        api_key=api_key,
        base_url=settings.football_data_base_url,
        timeout=settings.provider_timeout_seconds,
    )
    yield
    await app.state.provider.aclose()
    await engine.dispose()


app = FastAPI(title="Football League Table POC", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(leagues.router)


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
