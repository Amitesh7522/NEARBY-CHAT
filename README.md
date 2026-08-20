# Nearby Chat 📡💬

> Real-time social discovery and messaging web application built with **Python 3.14 / Django 6**, **Django Channels** (WebSockets), **PostgreSQL**, **Redis**, and a responsive **HTML5/CSS3/HTMX/Vanilla ES6** frontend with complete **English (en)** and **Hindi (hi)** localization.

---

## 🌟 Features Overview

- **Authentic Realtime Messaging**: 1-on-1 direct conversations powered by Django Channels WebSockets with persistent PostgreSQL history, read receipts, and typing indicators.
- **Atomic Random Chat Matchmaking**: Zero duplicate pairing, self-match prevention, and real-time radar search queue.
- **Community Rooms**: Topic-based public rooms with live group chat, member counters, and discovery categories.
- **Profile & Discovery**: Online presence indicators, bio, location, and customizable visibility controls.
- **Comprehensive Safety & Moderation**: Bidirectional blocking, violation incident reporting, and integrated Django Admin moderation workflow.
- **Localization**: English (`en`) and Hindi (`hi`) with runtime language switcher.
- **Clean Responsive Design**: Mobile bottom navigation bar (Home | Chats | Rooms | Profile) + top-left hamburger menu for Settings, Help & Support, Privacy Policy, Terms of Use, and Logout.

---

## 📁 Repository Structure

```
nearby_chat/
├── manage.py                      # Django CLI management entrypoint
├── nearby_chat/                   # Core Project Configuration
│   ├── settings/
│   │   ├── base.py                # Base settings, apps, i18n, channel layers
│   │   ├── development.py         # Local SQLite / Console OTP dev settings
│   │   └── production.py          # PostgreSQL / Redis / SSL production settings
│   ├── asgi.py                    # ASGI Daphne entrypoint for HTTP & WebSockets
│   ├── routing.py                 # WebSocket URL router
│   ├── urls.py                    # Master URL router
│   └── wsgi.py                    # WSGI entrypoint
├── apps/
│   ├── accounts/                  # Auth, Profiles, Verification, Deletion, Sessions
│   ├── chat/                      # Direct Messaging, History, Idempotency, Pagination
│   ├── matching/                  # Random Chat atomic matchmaking engine
│   ├── rooms/                     # Community Rooms, Memberships, Live Room Chat
│   ├── safety/                    # Blocking, Reporting, Moderation Workflow
│   ├── notifications/             # In-App Notifications & Presence
│   └── core/                      # Home Discovery, Settings, Legal, Context Processors
├── locale/                        # Gettext localization catalogs (en, hi)
├── static/                        # Design tokens, CSS components, icons, JS modules
├── templates/                     # Semantic Django HTML5 templates
├── tests/                         # Automated test suite (accounts, chat, matching, rooms, safety, websockets)
├── deployment/                    # Dockerfile, docker-compose.yml, nginx.conf
├── requirements.txt               # Production Python dependencies
├── EXTERNAL_SERVICES.md           # Third-party OTP, Email, DB & Redis guide
└── .env.example                   # Environment configuration template
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python**: 3.12+ (Tested on Python 3.14)
- **Pip**: 24+

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 4. Run Migrations & Seed Sample Data
```bash
python manage.py migrate
python manage.py seed_data
```

*The `seed_data` command creates:*
- **Admin**: `admin` / `admin12345`
- **Users**: `priya_sharma`, `rahul_verma`, `ananya_sen`, `aarav_patel`, `rohan_gupta` (Password for all: `password123`)
- **Public Rooms**: "Tech & Startups India", "Coffee & Conversations", "Music & Indie Beats", "Delhi / NCR Hangout"

### 5. Run Development Server (ASGI Daphne)
```bash
python manage.py runserver
```
Open **http://127.0.0.1:8000** in your browser.

---

## 🧪 Running Automated Tests

Run the full Django test suite:
```bash
python manage.py test tests
```

---

## 🐳 Production Deployment with Docker Compose

To start the complete production stack (PostgreSQL + Redis + ASGI Daphne + Nginx):
```bash
cd deployment
docker-compose --env-file ../.env up -d --build
```
