"""
WSGI config for Nearby Chat project.
"""
import os
from django.core.wsgi import get_wsgi_application

# Auto-detect cloud production environments (Railway, Render) if not explicitly set
if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RENDER') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nearby_chat.settings.production')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nearby_chat.settings.development')

application = get_wsgi_application()
