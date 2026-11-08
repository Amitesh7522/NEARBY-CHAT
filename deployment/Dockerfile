# ==============================================================================
# NEARBY CHAT — PRODUCTION DOCKERFILE
# Multi-stage Python 3.14 + ASGI Daphne Server
# ==============================================================================

FROM python:3.14-slim as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    DJANGO_SETTINGS_MODULE=nearby_chat.settings.production

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY . /app

# Collect static assets during build with dummy values so WhiteNoise compresses assets
RUN DATABASE_URL="sqlite:///dev/null" \
    DJANGO_SECRET_KEY="build-collectstatic-key" \
    python manage.py collectstatic --noinput --settings=nearby_chat.settings.production

# Run as non-root app user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Start ASGI Daphne server using dynamic $PORT assigned by Railway/Render
CMD ["sh", "-c", "python manage.py migrate --noinput && daphne -b 0.0.0.0 -p ${PORT:-8000} nearby_chat.asgi:application"]
