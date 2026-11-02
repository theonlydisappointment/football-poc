from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://football:football@localhost:5432/football"

    # SecretStr keeps the key out of reprs, tracebacks and logs.
    football_data_api_key: SecretStr = SecretStr("")
    football_data_base_url: str = "https://api.football-data.org/v4"
    provider_timeout_seconds: float = 10.0

    # A successful sync younger than this is served from Postgres without calling the provider.
    cache_ttl_seconds: int = 600

    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
