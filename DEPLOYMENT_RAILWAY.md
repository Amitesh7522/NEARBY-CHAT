# NearbyChat — Railway Staging & Production Deployment Guide

This guide provides complete, step-by-step instructions for deploying **NearbyChat** on [Railway](https://railway.app), leveraging ASGI (Daphne), Django Channels, PostgreSQL, Redis, WhiteNoise static file serving, Brevo transactional email OTP, and end-to-end encrypted Private Rooms.

---

## 1. Architectural Stack Overview

| Component | Technology | Configuration / Entrypoint |
| :--- | :--- | :--- |
| **Application Server** | Daphne (ASGI) | `daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application` |
| **Web Framework** | Django 5.0+ | `nearby_chat.settings.production` |
| **Realtime WebSockets** | Django Channels 4.1+ | `channels_redis.core.RedisChannelLayer` |
| **Primary Database** | PostgreSQL 16+ | Managed Railway PostgreSQL Service (`DATABASE_URL`) |
| **Channel Layer & Cache** | Redis 7+ | Managed Railway Redis Service (`REDIS_URL`) |
| **Static Asset Serving** | WhiteNoise 6.7+ | `whitenoise.storage.CompressedManifestStaticFilesStorage` |
| **Transactional Email / OTP**| Brevo REST API v3 | `https://api.brevo.com/v3/smtp/email` (`no-reply@nearbychat.in`) |
| **E2EE Private Rooms** | Web Crypto API (Client) | AES-GCM-256 + ECDH P-256 (Server stores ciphertext only) |
| **Health & Probes** | Zero-Leakage Endpoints | Liveness: `/health/` \| Readiness: `/health/ready/` |

---

## 2. Step-by-Step Railway Deployment Process

### Step 1: Create a Railway Project
1. Log in to [Railway Dashboard](https://railway.app/dashboard).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `nearby-chat` repository.

### Step 2: Provision PostgreSQL Database
1. In your Railway project canvas, click **+ New** -> **Database** -> **Add PostgreSQL**.
2. Railway will spin up a dedicated PostgreSQL instance and automatically generate `DATABASE_URL`, `DATABASE_PRIVATE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, and `PGDATABASE`.

### Step 3: Provision Redis Instance
1. In your Railway project canvas, click **+ New** -> **Database** -> **Add Redis**.
2. Railway will spin up a dedicated Redis instance and automatically generate `REDIS_URL` and `REDIS_PRIVATE_URL`.

### Step 4: Configure Railway Service Variables
In your Django Web Service on Railway, navigate to the **Variables** tab and set the following environment variables:

#### Core Django Settings
```env
DJANGO_SETTINGS_MODULE=nearby_chat.settings.production
DJANGO_SECRET_KEY=generate_a_secure_50_character_random_string_here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=nearbychat.in,www.nearbychat.in,.railway.app,.up.railway.app
CSRF_TRUSTED_ORIGINS=https://nearbychat.in,https://www.nearbychat.in,https://*.railway.app,https://*.up.railway.app
SECURE_SSL_REDIRECT=True
```

#### Database & Redis (Railway Private Networking)
Railway automatically links services when referenced in the same project:
```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
USE_REDIS=True
```
*(If using single-project auto-linking, Railway will automatically inject `DATABASE_URL` and `REDIS_URL` into your web service environment)*.

#### Brevo Transactional Email OTP Settings
```env
BREVO_API_KEY=your_live_brevo_v3_api_key
BREVO_SENDER_EMAIL=no-reply@nearbychat.in
BREVO_SENDER_NAME=Nearby Chat
```

---

## 3. Build & Start Commands

Railway uses `railway.json` and `Procfile` included in the root of the repository:

### `Procfile`
```procfile
web: daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
```

### `railway.json`
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application",
    "healthcheckPath": "/health/",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

- **Release Phase**: Automatically runs database migrations (`python manage.py migrate --noinput`) and compresses static assets (`python manage.py collectstatic --noinput`) before traffic is shifted to the new build.
- **Web Phase**: Starts the ASGI asynchronous Daphne server binding to all network interfaces (`0.0.0.0`) on the port dynamically allocated by Railway (`$PORT`).

---

## 4. Custom Domain & SSL/TLS Configuration

1. In Railway, open your web service -> **Settings** -> **Domains**.
2. Click **Custom Domain** and enter `nearbychat.in` (and optionally `www.nearbychat.in`).
3. Railway will display the required DNS records:
   - **Type**: `CNAME`
   - **Name**: `@` (or `www`)
   - **Value**: `<service-id>.up.railway.app`
4. Add these DNS records in your domain registrar / DNS provider (Cloudflare, Namecheap, GoDaddy, Route53).
5. Railway will automatically provision a valid Let's Encrypt SSL/TLS certificate.
6. HTTPS and WSS (secure WebSockets) are automatically terminated at Railway's edge reverse proxy.
7. NearbyChat's `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` ensures Django correctly identifies secure HTTPS/WSS requests.

---

## 5. Health Checks & Monitoring

NearbyChat provides dedicated, unauthenticated health probes designed for cloud orchestrators:

- **Liveness Probe**: `GET /health/`
  - Returns `{"status": "ok"}` with HTTP 200.
  - Used by Railway to verify process availability without hitting the database.
- **Readiness Probe**: `GET /health/ready/`
  - Validates PostgreSQL database connectivity and Redis cache availability.
  - Returns `{"status": "ready"}` with HTTP 200 (or `{"status": "degraded"}` with HTTP 503 if unreachable).
  - Sanitized: Never exposes internal stack traces, passwords, or connection strings.
- **Internal Diagnostics** (Optional): Passing the header `X-Health-Key: <HEALTH_CHECK_SECRET>` to `/health/ready/` returns detailed subsystem health metadata.

---

## 6. Zero-Downtime Releases & Rollback Plan

### Deploying Updates
1. Push code commits to your main/staging branch connected to Railway.
2. Railway triggers the Nixpacks builder.
3. The `release` phase executes migrations and static collection.
4. The new container launches Daphne.
5. Railway verifies `/health/` responds with HTTP 200 before routing live traffic.
6. The previous container is gracefully terminated.

### Instant Rollback
1. In Railway dashboard, go to the **Deployments** tab.
2. Find the previous stable deployment.
3. Click the three dots `...` and select **Rollback**.
4. Railway instantly shifts traffic back to the prior container image without rebuilding.

---

## 7. Troubleshooting & FAQ

### Issue 1: WebSockets connection fails with HTTP 403 (Origin Check)
- **Cause**: Django Channels `AllowedHostsOriginValidator` validates the `Origin` header against `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- **Fix**: Ensure your exact domain (e.g., `https://nearbychat.in` or `https://your-app.up.railway.app`) is in `CSRF_TRUSTED_ORIGINS` and `DJANGO_ALLOWED_HOSTS`.

### Issue 2: Brevo Email OTP returns 401 or delivery error
- **Cause**: `BREVO_API_KEY` is invalid or `BREVO_SENDER_EMAIL` (`no-reply@nearbychat.in`) is not an authenticated sender domain in Brevo dashboard.
- **Fix**: Log in to Brevo -> Senders & IP -> Senders, verify `no-reply@nearbychat.in`, and generate a fresh REST API v3 key.

### Issue 3: Missing Static Files or 404 on CSS/JS
- **Cause**: `collectstatic` was skipped or WhiteNoise failed to find files.
- **Fix**: WhiteNoise is enabled via `STORAGES` in `nearby_chat.settings.production`. Ensure the release phase `python manage.py collectstatic --noinput` ran successfully in deployment logs.
