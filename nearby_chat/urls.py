"""
URL Configuration for Nearby Chat.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    # Language switch endpoint
    path('i18n/', include('django.conf.urls.i18n')),
    
    # Internal Admin / Moderation
    path('admin/', admin.site.urls),
    
    # Core pages (Home, Legal, Help)
    path('', include('apps.core.urls')),
    
    # Authentication & Accounts
    path('accounts/', include('apps.accounts.urls')),
    
    # Direct Chats
    path('chats/', include('apps.chat.urls')),
    
    # Random Chat Matchmaking
    path('matching/', include('apps.matching.urls')),
    
    # Community Rooms
    path('rooms/', include('apps.rooms.urls')),
    
    # Safety, Blocking & Reporting
    path('safety/', include('apps.safety.urls')),
    
    # Notifications API
    path('notifications/', include('apps.notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
