"""Initial schema: leagues, standings, sync_runs. Seeds the six supported leagues.

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_LEAGUES = [
    {"code": "PL", "name": "Premier League", "country": "England"},
    {"code": "PD", "name": "La Liga", "country": "Spain"},
    {"code": "BL1", "name": "Bundesliga", "country": "Germany"},
    {"code": "SA", "name": "Serie A", "country": "Italy"},
    {"code": "FL1", "name": "Ligue 1", "country": "France"},
    {"code": "CL", "name": "Champions League", "country": "Europe"},
]


def upgrade() -> None:
    leagues = op.create_table(
        "leagues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.Text),
        sa.Column("emblem_url", sa.Text),
    )

    op.create_table(
        "standings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("season", sa.String(9), nullable=False),
        sa.Column("team_id", sa.Integer, nullable=False),
        sa.Column("team_name", sa.Text, nullable=False),
        sa.Column("team_crest", sa.Text),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("played", sa.Integer, nullable=False),
        sa.Column("won", sa.Integer, nullable=False),
        sa.Column("draw", sa.Integer, nullable=False),
        sa.Column("lost", sa.Integer, nullable=False),
        sa.Column("goals_for", sa.Integer, nullable=False),
        sa.Column("goals_against", sa.Integer, nullable=False),
        sa.Column("goal_difference", sa.Integer, nullable=False),
        sa.Column("points", sa.Integer, nullable=False),
        sa.Column("form", sa.String(20)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("league_id", "season", "team_id", name="uq_standings_league_season_team"),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("rows_written", sa.Integer),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('success', 'skipped', 'failed')", name="ck_sync_runs_status"),
    )

    op.bulk_insert(
        leagues,
        [
            {**league, "emblem_url": f"https://crests.football-data.org/{league['code']}.png"}
            for league in SEED_LEAGUES
        ],
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("standings")
    op.drop_table("leagues")
