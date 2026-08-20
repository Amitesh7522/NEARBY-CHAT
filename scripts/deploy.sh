#!/usr/bin/env bash
# ==============================================================================
# Nearby Chat — Automated Production Deployment Script
# Usage: ./scripts/deploy.sh
# ==============================================================================

set -e

echo "🚀 Starting Nearby Chat Production Deployment..."

# 1. Check for .env file
if [ ! -f .env ]; then
  echo "⚠️ .env file not found. Creating from .env.production.example..."
  cp .env.production.example .env
  echo "👉 Please edit .env with your production database credentials and secret key, then re-run this script."
  exit 1
fi

# 2. Build and start containers
echo "📦 Building and starting Docker containers..."
docker compose build --pull
docker compose up -d

# 3. Wait for database readiness
echo "⏳ Waiting for PostgreSQL to become ready..."
docker compose exec web python -c "
import time, os, psycopg2
for _ in range(30):
    try:
        psycopg2.connect(
            dbname=os.environ.get('DB_NAME', 'nearby_chat_db'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', 'postgres'),
            host=os.environ.get('DB_HOST', 'db'),
            port=os.environ.get('DB_PORT', '5432')
        )
        print('Database ready!')
        break
    except Exception:
        time.sleep(1)
" || true

# 4. Run database migrations
echo "🗄️ Running database migrations..."
docker compose exec web python manage.py migrate --noinput

# 5. Collect static assets
echo "🎨 Collecting static assets..."
docker compose exec web python manage.py collectstatic --noinput

echo "✅ Nearby Chat is successfully deployed and running!"
echo "🌐 Access your app at: http://localhost (or your configured domain)"
