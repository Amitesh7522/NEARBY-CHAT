"""
Production settings for Nearby Chat.
Optimized for Railway, Render, Docker, and Cloud deployments.
"""
import os
from pathlib import Path
from .base import *

# Safe dj_database_url import with built-in urlparse fallback
try:
    import dj_database_url
except ImportError:
    dj_database_url = None

def parse_database_url(url_str, conn_max_age=600):
    if dj_database_url:
        return dj_database_url.config(default=url_str, conn_max_age=conn_max_age, conn_health_checks=True)
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url_str)
    engine = 'django.db.backends.postgresql'
    if parsed.scheme in ('postgres', 'postgresql'):
        engine = 'django.db.backends.postgresql'
    elif parsed.scheme == 'sqlite':
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': parsed.path.lstrip('/')}
    return {
        'ENGINE': engine,
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': conn_max_age,
        'CONN_HEALTH_CHECKS': True,
    }

# Security: Never enable DEBUG in production
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 't')

# Secret Key validation
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', SECRET_KEY)

# Allowed Hosts Configuration
# Includes user custom hosts, Railway domains, Render domains, and production custom domain
raw_allowed_hosts = os.getenv(
    'DJANGO_ALLOWED_HOSTS',
    'nearbychat.in,www.nearbychat.in,localhost,127.0.0.1,.railway.app,.up.railway.app,.onrender.com'
)
ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(',') if h.strip()]

# Include Railway dynamic service domains if provided by Railway environment
if os.getenv('RAILWAY_PUBLIC_DOMAIN'):
    ALLOWED_HOSTS.append(os.getenv('RAILWAY_PUBLIC_DOMAIN').strip())
if os.getenv('RAILWAY_STATIC_URL'):
    ALLOWED_HOSTS.append(os.getenv('RAILWAY_STATIC_URL').strip())

# Remove duplicates while preserving order
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

# CSRF Trusted Origins Configuration (Required for HTTPS POST / WebSockets in Django 4.0+)
raw_csrf_origins = os.getenv(
    'CSRF_TRUSTED_ORIGINS',
    'https://nearbychat.in,https://www.nearbychat.in,https://*.railway.app,https://*.up.railway.app,https://*.onrender.com'
)
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in raw_csrf_origins.split(',') if origin.strip()]

if os.getenv('RAILWAY_PUBLIC_DOMAIN'):
    railway_domain_origin = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN').strip()}"
    if railway_domain_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(railway_domain_origin)

# Database Configuration
# Supports Railway DATABASE_PRIVATE_URL, DATABASE_URL, or individual PG* / DB_* vars
DATABASE_URL = os.getenv('DATABASE_PRIVATE_URL') or os.getenv('DATABASE_URL') or os.getenv('DATABASE_PUBLIC_URL')

if DATABASE_URL:
    DATABASES = {
        'default': parse_database_url(DATABASE_URL, conn_max_age=600)
    }
elif os.getenv('PGHOST') or os.getenv('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('PGDATABASE') or os.getenv('DB_NAME', 'nearby_chat_prod'),
            'USER': os.getenv('PGUSER') or os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('PGPASSWORD') or os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('PGHOST') or os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('PGPORT') or os.getenv('DB_PORT', '5432'),
            'CONN_MAX_AGE': 600,
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    # Fallback to base sqlite database for offline build/asset generation steps
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Channels & Real-Time WebSocket Layer
# Supports Railway REDIS_PRIVATE_URL or standard REDIS_URL
USE_REDIS = os.getenv('USE_REDIS', 'True').lower() in ('true', '1', 't')
REDIS_URL = os.getenv('REDIS_PRIVATE_URL') or os.getenv('REDIS_URL')

if USE_REDIS and REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
    # Also configure Django Cache backend to use Redis when available
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    if USE_REDIS and not DEBUG and os.getenv('STRICT_REDIS', 'False').lower() in ('true', '1', 't'):
        raise RuntimeError("REDIS_URL or REDIS_PRIVATE_URL environment variable is required when USE_REDIS is enabled in production.")
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# Static Assets Serving with WhiteNoise
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

try:
    import whitenoise
    STATICFILES_STORAGE_BACKEND = "whitenoise.storage.CompressedManifestStaticFilesStorage"
except ImportError:
    STATICFILES_STORAGE_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": STATICFILES_STORAGE_BACKEND,
    },
}

# Reverse Proxy & Security Hardening (Railway / Render / Cloudflare / Nginx)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 't')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Email Configuration (Brevo REST API / SMTP fallback)
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')
BREVO_SENDER_EMAIL = os.getenv('BREVO_SENDER_EMAIL', 'no-reply@nearbychat.in')
BREVO_SENDER_NAME = os.getenv('BREVO_SENDER_NAME', 'Nearby Chat')

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Nearby Chat <no-reply@nearbychat.in>')

# Production Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
