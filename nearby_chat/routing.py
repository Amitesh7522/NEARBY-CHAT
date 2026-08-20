"""
WebSocket routing for Nearby Chat.
"""
from django.urls import re_path, path
from apps.chat import consumers as chat_consumers
from apps.rooms import consumers as room_consumers
from apps.matching import consumers as matching_consumers
from apps.notifications import consumers as notification_consumers

websocket_urlpatterns = [
    # Direct 1-on-1 Chat WebSocket
    re_path(r'^ws/chat/(?P<conversation_id>[0-9a-f-]+)/$', chat_consumers.ChatConsumer.as_asgi()),
    
    # Community Room WebSocket
    re_path(r'^ws/rooms/(?P<room_id>[0-9a-f-]+)/$', room_consumers.RoomConsumer.as_asgi()),
    
    # Random Chat Matchmaking WebSocket
    re_path(r'^ws/matching/$', matching_consumers.MatchingConsumer.as_asgi()),
    
    # User Notification & Online Presence WebSocket
    re_path(r'^ws/notifications/$', notification_consumers.NotificationConsumer.as_asgi()),
]
