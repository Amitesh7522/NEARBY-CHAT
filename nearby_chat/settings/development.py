"""
Development settings for Nearby Chat.
"""
from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Development database (SQLite for local ease, can switch to PostgreSQL via env)
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite')

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'nearby_chat_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Email backend for development (outputs to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# SMS/OTP test mode logger
OTP_DEV_MODE = True
