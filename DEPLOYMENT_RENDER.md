# NearbyChat — Render Production Deployment Guide

This guide provides step-by-step instructions for deploying **NearbyChat** on [Render](https://render.com) using ASGI (Daphne), Django Channels, managed PostgreSQL, WhiteNoise, and Brevo transactional email OTP.

---

## 1. Quick Deploy via Render Blueprint (Recommended)

NearbyChat includes a [`render.yaml`](file:///C:/Users/amite/.gemini/antigravity/scratch/nearby_chat/render.yaml) Blueprint in the root directory that automatically provisions:
1. **NearbyChat Web Service** (Python 3.11+, Daphne ASGI, WebSockets enabled).
2. **Managed PostgreSQL Database** (`nearby-chat-db` on Starter plan).

### Deployment Steps:
1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub repository (`Amitesh7522/NEARBY-CHAT`).
4. Render will read `render.yaml` and display the resources to create:
   - **Service**: `nearby-chat` (Web Service, Region: Singapore)
   - **Database**: `nearby-chat-db` (PostgreSQL)
5. Click **Apply**.
6. Once created, go to the `nearby-chat` Web Service → **Environment** tab:
   - Add your secret `BREVO_API_KEY` (obtained from Brevo dashboard).
7. Render will build and deploy automatically!

---

## 2. Manual Web Service & Database Setup (Alternative)

If you prefer to configure the services manually in the Render dashboard:

### Step 1: Create Managed PostgreSQL Database
1. In Render Dashboard, click **New +** → **PostgreSQL**.
2. Name: `nearby-chat-db`
3. Database: `nearby_chat`
4. User: `nearby_chat_user`
5. Region: `Singapore` (low latency for India)
6. Plan: `Starter` (or `Free` for initial testing)
7. Click **Create Database** and copy the **Internal Database URL**.

### Step 2: Create Web Service
1. Click **New +** → **Web Service**.
2. Connect your GitHub repository.
3. Configure the service settings:
   - **Name**: `nearby-chat`
   - **Region**: `Singapore`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput`
   - **Start Command**: `daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application`
   - **Plan**: `Starter` ($7/mo with 24/7 uptime & persistent WebSockets)

### Step 3: Add Environment Variables
In the **Environment** tab, set:

| Key | Value |
| :--- | :--- |
| `DJANGO_SETTINGS_MODULE` | `nearby_chat.settings.production` |
| `DJANGO_SECRET_KEY` | *(Click "Generate" or provide a secure 50+ char random string)* |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `nearbychat.in,www.nearbychat.in,.onrender.com,localhost` |
| `CSRF_TRUSTED_ORIGINS` | `https://nearbychat.in,https://www.nearbychat.in,https://*.onrender.com` |
| `SECURE_SSL_REDIRECT` | `True` |
| `DATABASE_URL` | *(Paste Internal Database URL from Step 1)* |
| `BREVO_API_KEY` | *(Your live Brevo API Key)* |
| `BREVO_SENDER_EMAIL` | `no-reply@nearbychat.in` |
| `BREVO_SENDER_NAME` | `Nearby Chat` |

---

## 3. Health & Probes

NearbyChat includes unauthenticated health check endpoints:
- **Liveness Probe**: `GET /health/` → Returns `{"status": "ok"}` with HTTP 200.
- **Readiness Probe**: `GET /health/ready/` → Validates DB & cache, returns `{"status": "ready"}` with HTTP 200.

In Render Web Service **Settings** → **Health Check Path**, enter: `/health/`.

---

## 4. Custom Domain & SSL (`nearbychat.in`)

1. In Render Web Service → **Settings** → **Custom Domains**, click **Add Custom Domain**.
2. Enter `nearbychat.in` and `www.nearbychat.in`.
3. Add the DNS records shown by Render in your DNS registrar (Cloudflare / Namecheap / GoDaddy):
   - **ANAME/ALIAS or CNAME** pointing `@` and `www` to `nearby-chat.onrender.com`.
4. Render will automatically issue and renew a free Let's Encrypt SSL/TLS certificate.
