#!/bin/sh
set -e

# Run database migrations
echo "==> Running database migrations..."
python manage.py migrate --noinput

# Start ASGI Daphne server with dynamic PORT expansion
PORT="${PORT:-8000}"
echo "==> Starting Daphne ASGI server on port ${PORT}..."
exec python -m daphne -b 0.0.0.0 -p "${PORT}" nearby_chat.asgi:application
