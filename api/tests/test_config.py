"""Config: hosted-Postgres URL handling and dependency lists staying in sync."""

import tomllib
from pathlib import Path

import pytest

from app.config import Settings, to_asyncpg_url

API_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Neon / Vercel Marketplace style
        (
            "postgres://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?ssl=require",
        ),
        ("postgresql://u:p@db.example.com:6543/app", "postgresql+asyncpg://u:p@db.example.com:6543/app"),
        # Already asyncpg-ready (Docker Compose): unchanged
        (
            "postgresql+asyncpg://football:football@db:5432/football",
            "postgresql+asyncpg://football:football@db:5432/football",
        ),
    ],
)
def test_to_asyncpg_url(raw, expected):
    assert to_asyncpg_url(raw) == expected


def test_unpooled_url_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgres://u:p@ep-x.neon.tech/db?sslmode=require")
    assert Settings(_env_file=None).database_url == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"


def test_requirements_txt_matches_pyproject():
    pyproject = tomllib.loads((API_DIR / "pyproject.toml").read_text())["project"]["dependencies"]
    requirements = [
        line.strip() for line in (API_DIR / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert sorted(pyproject) == sorted(requirements)
