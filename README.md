# Football League Table POC

Pick a league, click **Pull League Data**, and see the current table. The FastAPI backend fetches
standings from [football-data.org](https://www.football-data.org), stores them in PostgreSQL, and
returns the stored rows. A React page renders them.

```
React (Vite)  ──►  FastAPI  ──►  football-data.org v4
                      │
                      └────►  PostgreSQL 16
```

How it works, file by file: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).
Architecture, resources and deployment (with diagrams): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quickstart

1. Get a free API key at <https://www.football-data.org/client/register>.
2. Create `.env`:

   ```bash
   cp .env.example .env
   ```

   Set `FOOTBALL_DATA_API_KEY=<your key>`. Leave the other values as they are.
3. Start everything:

   ```bash
   docker compose up --build
   ```

4. Open <http://localhost:5173>.

| Service | URL | Notes |
| --- | --- | --- |
| `web` | http://localhost:5173 | Vite dev server |
| `api` | http://localhost:8000 | OpenAPI docs at `/docs`. Runs `alembic upgrade head` on start. |
| `db` | localhost:5432 | user / password / db: `football` |

The API container needs outbound HTTPS to `api.football-data.org`.

## Environment variables

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `FOOTBALL_DATA_API_KEY` | api | *(empty)* | Provider key. Without it, syncs return 502 with a clear message. |
| `DATABASE_URL` | api | `postgresql+asyncpg://football:football@db:5432/football` | Async SQLAlchemy URL |
| `VITE_API_URL` | web | `http://localhost:8000` | Where the browser sends API calls |
| `CORS_ORIGINS` | api | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API |
| `DB_HOST_PORT` | compose | `5432` | Host port for Postgres, if 5432 is taken |

## API

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/api/leagues` | Seeded leagues `[{code, name, country, emblem_url}]` |
| POST | `/api/leagues/{code}/sync` | Fetch from the provider (or reuse a sync under 10 min old), upsert, return the stored table |
| GET | `/api/leagues/{code}/standings` | Stored table only, no provider call |
| GET | `/health` | DB ping → `{"status": "ok"}` |

`sync` and `standings` return `{league, season, fetched_at, source: "live" | "cache", rows: [...]}`.
Provider failures return **502** `{detail, last_known}`. Unknown codes return **404**.

## Tests

The tests run against a real Postgres database, `football_test`, on the compose `db` service.
They create it if needed and run the Alembic migrations on it. The provider is stubbed, so no key
or network is needed.

```bash
docker compose run --rm api pytest
```

## Useful commands

```bash
# Every stored row for a league
docker compose exec db psql -U football -c "SELECT position, team_name, points FROM standings s JOIN leagues l ON l.id = s.league_id WHERE l.code = 'PL' ORDER BY position;"

# Sync history
docker compose exec db psql -U football -c "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 10;"

# Wipe the database and start fresh
docker compose down -v
```

## Frontend without Docker (hot reload)

```bash
cd web && npm install && npm run dev
```

The API still needs to be running (`docker compose up db api`). With no `VITE_API_URL` set, the
Vite dev server forwards `/api` and `/health` to `localhost:8000`.

## Deploy to Vercel

`vercel.json` deploys both halves as one Vercel project using **Services**:
- `web` builds the Vite app and serves `/`.
- `api` runs FastAPI and handles `/api/*` and `/health`.

They share a domain, so no CORS setup is needed. Each build runs `alembic upgrade head`
(`[tool.vercel.scripts]` in `api/pyproject.toml`), so the hosted database is migrated before the
new code goes live.

One-time setup in the Vercel project:
1. **Storage → Create Database → Neon (Postgres)**, connected to the project for all
   environments. This adds `DATABASE_URL` and `DATABASE_URL_UNPOOLED`. The API prefers the
   unpooled URL, and converts `postgres://…?sslmode=require` URLs for asyncpg itself.
2. **Settings → Environment Variables:** add `FOOTBALL_DATA_API_KEY` and mark it Sensitive.
3. Deploy. Pushes to `main` deploy to production from then on.
