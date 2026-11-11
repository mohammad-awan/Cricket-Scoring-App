# Cricket Intelligence Platform — Stage 1

Stage 1 provides a clean FastAPI foundation using SQLAlchemy 2.x
async ORM, Alembic migrations, and a private Supabase PostgreSQL
connection.

It intentionally contains no cricket feature tables and no
authentication yet.

## Install

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Configure Supabase

Copy the environment example:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace `DATABASE_URL` with the connection string
from Supabase Dashboard -> Connect -> Session pooler.

Use the `postgresql+psycopg://` scheme and ensure SSL is enabled:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

Never commit `.env` and never expose `DATABASE_URL` to a frontend.

## Apply migration

```bash
alembic upgrade head
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health

## Run tests

```bash
pytest
```

Run the real Supabase integration test:

PowerShell:

```powershell
$env:RUN_LIVE_DB_TESTS="1"
pytest -m integration
```

macOS/Linux:

```bash
RUN_LIVE_DB_TESTS=1 pytest -m integration
```

## Future migration workflow

After creating or modifying ORM models:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Always review generated migrations before applying them.

Do not call `Base.metadata.create_all()`. Alembic owns all schema
changes.

## Stage 12 fixture workspace

Open a tournament and select **Fixtures**, or visit
`/competitions/{tournament_id}/fixtures`. Approve participating teams and
assign active venues in the tournament workspace first.

The builder supports manual CSV entry, reproducible random draws, circle-method
round robins, groups, and knockout previews. Saving creates a draft; explicit
confirmation validates the complete schedule and links playable Match records
atomically. Later bracket slots wait for finalized results. Group qualifiers
remain blocked until official Stage 13 rankings are available.

The UI uses the existing vanilla JavaScript and CSS; no frontend build is needed.
Install the updated Python requirements for timezone data on Windows.
Scheduling uses a deterministic feasibility-first heuristic; its reported score
describes rest and venue imbalance, and does not claim a globally optimal draw.
No historical ratings or win probabilities are invented.

```powershell
$env:DEBUG="false"
.\.venv\Scripts\python.exe -m pytest tests/unit tests/api -q
node --test tests/frontend/*.test.cjs
```

Fixture database integration tests require a separate, migrated PostgreSQL
database in `TEST_DATABASE_URL`. They roll back an outer transaction and never
fall back to the application's configured database.
