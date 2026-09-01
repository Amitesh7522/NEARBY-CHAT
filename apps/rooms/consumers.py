"""
Django Channels WebSocket Consumer for Community Rooms.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .services import RoomService
from .models import Room, RoomMember

logger = logging.getLogger(__name__)

class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        from apps.core.security import validate_websocket_origin
        if not validate_websocket_origin(self.scope):
            logger.warning("RoomConsumer connection rejected: Invalid or unauthorized Origin header")
            await self.close(code=4003)
            return

        self.user = self.scope.get('user')
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f"room_{self.room_id}"

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Ensure user is a member of the room
        is_member = await self._is_room_member()
        if not is_member:
            # Auto-join if public
            can_join = await self._auto_join_if_public()
            if not can_join:
                await self.close(code=4003)
                return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        action = content.get('action')

        if action == 'send_message':
            text = content.get('content', '').strip()
            client_msg_id = content.get('client_msg_id', '')
            if not text:
                return

            if len(text) > 5000:
                await self.send_json({'type': 'error', 'message': 'Message exceeds maximum allowed length (5000 characters).'})
                return

            try:
                msg_data = await database_sync_to_async(RoomService.send_room_message)(
                    room_id=self.room_id,
                    sender=self.user,
                    content=text,
                    client_msg_id=client_msg_id
                )

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'room_message_event',
                        'message_id': msg_data['id'],
                        'client_msg_id': msg_data['client_msg_id'],
                        'sender_id': msg_data['sender_id'],
                        'sender_username': msg_data['sender_username'],
                        'sender_name': msg_data['sender_name'],
                        'sender_avatar': msg_data['sender_avatar'],
                        'content': msg_data['content'],
                        'created_at': msg_data['created_at'],
                    }
                )
            except Exception as e:
                logger.error(f"Error sending room message: {e}")
                err_text = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                await self.send_json({
                    'type': 'error',
                    'message': err_text
                })

    async def room_message_event(self, event):
        await self.send_json({
            'type': 'room_message',
            'message_id': event['message_id'],
            'client_msg_id': event['client_msg_id'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'sender_name': event['sender_name'],
            'sender_avatar': event['sender_avatar'],
            'content': event['content'],
            'created_at': event['created_at'],
        })

    @database_sync_to_async
    def _is_room_member(self):
        return RoomMember.objects.filter(room_id=self.room_id, user=self.user).exists()

    @database_sync_to_async
    def _auto_join_if_public(self):
        room = Room.objects.filter(id=self.room_id).first()
        if room and room.is_public:
            RoomService.join_room(self.user, room)
            return True
        return False
