import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import nearby_chat.routing
from apps.chat.models import Conversation, ConversationParticipant
from apps.rooms.models import Room, RoomMember

User = get_user_model()

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_chat_websocket_unauthenticated_rejection():
    """Unauthenticated WebSocket connection is rejected with 4001."""
    application = URLRouter(nearby_chat.routing.websocket_urlpatterns)
    communicator = WebsocketCommunicator(
        application,
        "/ws/chat/00000000-0000-0000-0000-000000000000/"
    )
    connected, code = await communicator.connect()
    assert not connected or code in [4001, 4003]
    await communicator.disconnect()

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_matching_websocket_unauthenticated_rejection():
    """Unauthenticated matching WebSocket connection is rejected."""
    application = URLRouter(nearby_chat.routing.websocket_urlpatterns)
    communicator = WebsocketCommunicator(
        application,
        "/ws/matching/"
    )
    connected, code = await communicator.connect()
    assert not connected or code in [4001, 4003]
    await communicator.disconnect()
