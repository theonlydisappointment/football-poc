from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)

# expire_on_commit=False: ORM objects stay readable after commit. Without it, touching
# an attribute after commit would trigger a lazy reload, which async SQLAlchemy forbids.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed (and rolled back if needed) afterwards."""
    async with SessionLocal() as session:
        yield session
