# External Services & Provider Integration Guide

Nearby Chat is engineered with a **zero fake functionality** policy. All third-party capabilities are cleanly decoupled using modular provider adapters.

---

## 1. SMS & Phone OTP Verification (India & Global)

| Provider | Why Needed | Free Tier / Dev Option | Paid / Production Cost | Account Registration | Credentials to Configure in `.env` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Console Logger (Default)** | Development & zero-cost testing | Free forever. Logs OTP code directly to terminal/stdout. | ₹0 | None required | `OTP_PROVIDER=console` |
| **MSG91 (India DLT Compliant)** | Production transactional SMS OTP across all Indian telecom operators | 25,000 free test SMS credits for startups upon verification | ~₹0.18 to ₹0.25 per SMS + DLT registration fees | [msg91.com](https://msg91.com/) | `OTP_PROVIDER=msg91`<br>`MSG91_AUTH_KEY=...`<br>`MSG91_TEMPLATE_ID=...` |
| **Fast2SMS (India)** | Instant SMS gateway for Indian mobile numbers without mandatory DLT upfront for dev | ₹50 free testing wallet upon sign up | ~₹0.15 to ₹0.20 per SMS | [fast2sms.com](https://www.fast2sms.com/) | `OTP_PROVIDER=fast2sms`<br>`FAST2SMS_API_KEY=...` |
| **Twilio (Global)** | Worldwide SMS delivery & phone verification | $15 free trial balance with verified phone | ~$0.0079 per SMS (US/EU) / ~$0.04 (India) | [twilio.com](https://www.twilio.com/) | `OTP_PROVIDER=twilio`<br>`TWILIO_ACCOUNT_SID=...`<br>`TWILIO_AUTH_TOKEN=...` |

---

## 2. Transactional Email

| Provider | Why Needed | Free Option | Production Cost | Registration Link | Credentials |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Console Backend** | Local email logging | Free (terminal output) | ₹0 | None | `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` |
| **SendGrid** | Production email delivery | 100 emails/day free forever | $19.95/month for 50k emails | [sendgrid.com](https://sendgrid.com/) | `EMAIL_HOST=smtp.sendgrid.net`<br>`EMAIL_HOST_USER=apikey`<br>`EMAIL_HOST_PASSWORD=...` |
| **AWS SES** | Scalable enterprise email delivery | 62,000 free emails/month when hosted on EC2 | $0.10 per 1,000 emails | [aws.amazon.com/ses](https://aws.amazon.com/ses/) | `EMAIL_HOST=email-smtp.us-east-1.amazonaws.com`<br>`EMAIL_HOST_USER=...`<br>`EMAIL_HOST_PASSWORD=...` |

---

## 3. Production PostgreSQL Database

| Provider | Free Option | Paid Option | Setup Instructions |
| :--- | :--- | :--- | :--- |
| **Local SQLite** | Free, zero configuration (default dev mode). | N/A | `DB_ENGINE=sqlite` |
| **Supabase PostgreSQL** | 500 MB free database | $25/month for Pro | 1. Create project on [supabase.com](https://supabase.com/).<br>2. Copy connection string to `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. |
| **Neon Serverless Postgres** | 0.5 GB storage free | $19/month | Create database on [neon.tech](https://neon.tech/). |
| **Self-Hosted PostgreSQL** | Included in `docker-compose.yml` | Cost of your VPS ($5-10/mo) | Run `docker-compose up -d db`. |

---

## 4. Redis Channel Layer & Cache

| Provider | Free Option | Paid Option | Setup Instructions |
| :--- | :--- | :--- | :--- |
| **InMemory Channel Layer** | Free (built-in Django Channels layer for local dev) | N/A | `USE_REDIS=False` |
| **Upstash Redis** | 10,000 commands/day free | Pay-as-you-go ($0.20 per 100k requests) | Create Redis instance on [upstash.com](https://upstash.com/) and paste URI into `REDIS_URL`. |
| **Self-Hosted Redis** | Included in `docker-compose.yml` | Cost of your VPS | Run `docker-compose up -d redis`. |
