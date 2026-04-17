#!/bin/bash
set -e

export PYTHONPATH="/app:${PYTHONPATH}"

# ── Validate required env vars ──────────────────────────────────────────────
if [ -z "$DATABASE_URL" ]; then
  echo "ERROR: DATABASE_URL is not set."
  exit 1
fi

# Rewrite common sync URLs to async SQLAlchemy URLs if needed.
export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')
export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^mysql://|mysql+aiomysql://|')

# ── Wait for database (local dev only) ───────────────────────────────────────
# Supabase/managed DBs require SSL — nc can't check them. Skip in production.
if [ "$ENVIRONMENT" != "production" ]; then
  DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
  DB_HOST="${DB_HOST:-db}"
  if echo "$DATABASE_URL" | grep -q '^mysql+aiomysql://'; then
    DB_PORT="${DB_PORT:-3306}"
  else
    DB_PORT="${DB_PORT:-5432}"
  fi
  echo "Waiting for database at $DB_HOST:$DB_PORT..."
  for i in $(seq 1 30); do
    nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null && break
    if [ "$i" -eq 30 ]; then
      echo "ERROR: Database at $DB_HOST:$DB_PORT not reachable after 30s"
      exit 1
    fi
    sleep 1
  done
  echo "Database is ready!"
fi

# ── Run migrations ──────────────────────────────────────────────────────────
if echo "$DATABASE_URL" | grep -q '^mysql+aiomysql://'; then
  echo "Initializing MySQL schema from SQLAlchemy models..."
  python scripts/init_db.py
else
  echo "Running database migrations..."
  alembic upgrade head
fi

# ── Start the FastAPI application ───────────────────────────────────────────
PORT="${PORT:-10000}"
echo "Starting FastAPI application on port $PORT..."
if [ "$ENVIRONMENT" = "development" ]; then
  uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
else
  uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
fi
