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

# Create virtual environment in /opt/venv (globally accessible, outside /root)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final Runtime Image
FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=nearby_chat.settings.production

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder and ensure read/executable permissions for all users
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rx /opt/venv

COPY . /app

# Collect static assets during build with dummy values so WhiteNoise compresses assets
RUN DATABASE_URL="sqlite:///dev/null" \
    DJANGO_SECRET_KEY="build-collectstatic-key" \
    python manage.py collectstatic --noinput --settings=nearby_chat.settings.production

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Create non-root runtime user and set ownership of /app
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Start ASGI Daphne server via entrypoint script with dynamic $PORT expansion
CMD ["sh", "/app/entrypoint.sh"]
