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