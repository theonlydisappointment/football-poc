from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def to_asyncpg_url(raw: str) -> str:
    """Accept the URL formats hosted Postgres providers hand out and make them asyncpg-ready.

    "postgres://u:p@host/db?sslmode=require&channel_binding=require"
      -> "postgresql+asyncpg://u:p@host/db?ssl=require"
    """
    url = make_url(raw)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # libpq-only option; asyncpg rejects it
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode  # asyncpg takes the same values: require, verify-full, ...
    return url.set(query=query).render_as_string(hide_password=False)


class Settings(BaseSettings):
    """All runtime config, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DATABASE_URL_UNPOOLED (set by Vercel's Neon integration) wins when present: a direct
    # connection avoids PgBouncer's limits on asyncpg's prepared statements.
    database_url: str = Field(
        default="postgresql+asyncpg://football:football@localhost:5432/football",
        validation_alias=AliasChoices("DATABASE_URL_UNPOOLED", "DATABASE_URL"),
    )

    # SecretStr keeps the key out of reprs, tracebacks and logs.
    football_data_api_key: SecretStr = SecretStr("")
    football_data_base_url: str = "https://api.football-data.org/v4"
    provider_timeout_seconds: float = 10.0

    # A successful sync younger than this is served from Postgres without calling the provider.
    cache_ttl_seconds: int = 600

    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        return to_asyncpg_url(value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
