#!/bin/bash
set -e

# ── Validate required env vars ──────────────────────────────────────────────
if [ -z "$DATABASE_URL" ]; then
  echo "ERROR: DATABASE_URL is not set. Set it in the Render dashboard."
  exit 1
fi

# Rewrite Render's postgresql:// URL to postgresql+asyncpg:// if needed
export DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql://|postgresql+asyncpg://|')

# ── Wait for database (local dev only) ───────────────────────────────────────
# Supabase/managed DBs require SSL — nc can't check them. Skip in production.
if [ "$ENVIRONMENT" != "production" ]; then
  DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
  DB_HOST="${DB_HOST:-db}"
  DB_PORT="${DB_PORT:-5432}"
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
echo "Running database migrations..."
alembic upgrade head

# ── Start the FastAPI application ───────────────────────────────────────────
PORT="${PORT:-10000}"
echo "Starting FastAPI application on port $PORT..."
if [ "$ENVIRONMENT" = "development" ]; then
  uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
else
  uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
fi
