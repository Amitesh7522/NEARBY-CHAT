"""
ASGI config for Nearby Chat project.
Handles both HTTP and WebSocket protocols using Django Channels.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nearby_chat.settings.development')
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import nearby_chat.routing

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                nearby_chat.routing.websocket_urlpatterns
            )
        )
    ),
})
