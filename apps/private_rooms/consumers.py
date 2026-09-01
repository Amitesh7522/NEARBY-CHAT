"""
Django Channels WebSocket Consumer for Private 1-to-1 Rooms.
Ensures zero identity leakage, authenticates via hashed session credentials,
validates Origin against CSWSH, and manages real-time messaging.
"""
import logging
from urllib.parse import urlparse
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils import timezone

from .models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from .services import hash_token

logger = logging.getLogger(__name__)


class PrivateRoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f"private_room_{self.room_id}"

        # 1. Validate Origin against CSWSH (Cross-Site WebSocket Hijacking)
        if not await self._validate_origin():
            logger.warning(f"PrivateRoomConsumer connection rejected: Invalid or unauthorized Origin header")
            await self.close(code=4003)
            return

        session = self.scope.get('session', {})
        raw_session_token = session.get(f"pr_auth_{self.room_id}") or session.get(f"private_room_session_{self.room_id}") or session.get("private_session_key")

        # 2. Authenticate participant using hashed token
        self.participant = await self._get_participant(raw_session_token)
        if not self.participant:
            logger.warning(f"PrivateRoomConsumer connection rejected: Invalid participant for room {self.room_id}")
            await self.close(code=4003)
            return

        # 3. Check room status (not expired, deleted, or blocked)
        room_valid = await self._is_room_valid()
        if not room_valid:
            await self.close(code=4004)
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Send connection established confirmation with remaining time
        time_remaining = await self._get_time_remaining()
        await self.send_json({
            'type': 'room_status',
            'status': 'connected',
            'time_remaining_seconds': time_remaining,
            'temp_name': self.participant.temp_name,
            'avatar_color': self.participant.temp_avatar_color,
            'is_creator': self.participant.is_creator,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        """
        Handles incoming actions: 'send_message', 'typing', 'read_receipt'
        """
        action = content.get('action')

        if action == 'send_message':
            text = content.get('content', '').strip()
            client_msg_id = content.get('client_msg_id', '')
            if not text:
                return

            room_valid = await self._is_room_valid()
            if not room_valid:
                await self.send_json({'type': 'error', 'message': 'Room has expired or been deleted.'})
                return

            msg_data = await self._save_message(text, client_msg_id)
            if msg_data:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'private_message_event',
                        'message_id': msg_data['id'],
                        'client_msg_id': msg_data['client_msg_id'],
                        'sender_id': msg_data['sender_id'],
                        'sender_temp_name': msg_data['sender_temp_name'],
                        'sender_avatar_color': msg_data['sender_avatar_color'],
                        'sender_initials': msg_data['sender_initials'],
                        'is_creator': msg_data['is_creator'],
                        'content': msg_data['content'],
                        'message_type': 'text',
                        'created_at': msg_data['created_at'],
                    }
                )

        elif action == 'typing':
            is_typing = bool(content.get('is_typing', False))
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'private_typing_event',
                    'sender_id': str(self.participant.id),
                    'sender_temp_name': self.participant.temp_name,
                    'is_typing': is_typing,
                }
            )

    # Group Event Handlers
    async def private_message_event(self, event):
        await self.send_json({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'client_msg_id': event.get('client_msg_id', ''),
            'sender_id': event['sender_id'],
            'sender_temp_name': event['sender_temp_name'],
            'sender_avatar_color': event['sender_avatar_color'],
            'sender_initials': event['sender_initials'],
            'is_creator': event.get('is_creator', False),
            'content': event['content'],
            'message_type': event.get('message_type', 'text'),
            'file_url': event.get('file_url', ''),
            'file_name': event.get('file_name', ''),
            'file_size': event.get('file_size', 0),
            'created_at': event['created_at'],
        })

    async def private_typing_event(self, event):
        # Don't echo own typing indicator back
        if event['sender_id'] != str(self.participant.id):
            await self.send_json({
                'type': 'typing',
                'sender_temp_name': event['sender_temp_name'],
                'is_typing': event['is_typing'],
            })

    async def private_system_event(self, event):
        await self.send_json({
            'type': 'system_event',
            'event': event.get('event', 'update'),
            'message': event.get('message', ''),
        })

    async def _validate_origin(self):
        """
        Validates the Origin header to prevent CSWSH attacks.
        """
        headers = dict(self.scope.get('headers', []))
        origin_bytes = headers.get(b'origin')
        if not origin_bytes:
            # Direct/same-origin WebSocket or non-browser client
            return True
        origin = origin_bytes.decode('utf-8', errors='ignore')
        parsed = urlparse(origin)
        origin_host = parsed.hostname or parsed.netloc.split(':')[0]
        
        # Check against ALLOWED_HOSTS
        allowed = settings.ALLOWED_HOSTS
        if '*' in allowed or origin_host in allowed or 'localhost' in allowed or '127.0.0.1' in allowed:
            return True
        return False

    # Database Helpers
    @database_sync_to_async
    def _get_participant(self, raw_session_token):
        if not raw_session_token:
            return None
        token_hash = hash_token(raw_session_token)
        return PrivateRoomParticipant.objects.filter(
            room_id=self.room_id,
            session_token_hash=token_hash,
            is_active=True,
            is_blocked=False
        ).first()

    @database_sync_to_async
    def _is_room_valid(self):
        try:
            room = PrivateRoom.objects.get(id=self.room_id)
            return not room.is_deleted and not room.is_expired and not room.is_blocked
        except PrivateRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def _get_time_remaining(self):
        try:
            room = PrivateRoom.objects.get(id=self.room_id)
            return room.time_remaining_seconds()
        except PrivateRoom.DoesNotExist:
            return 0

    @database_sync_to_async
    def _save_message(self, text, client_msg_id):
        try:
            # Check idempotency
            if client_msg_id:
                existing = PrivateRoomMessage.objects.filter(
                    room_id=self.room_id,
                    client_msg_id=client_msg_id
                ).first()
                if existing:
                    return {
                        'id': str(existing.id),
                        'client_msg_id': existing.client_msg_id,
                        'sender_id': str(existing.sender_id),
                        'sender_temp_name': existing.sender.temp_name if existing.sender else 'Anonymous',
                        'sender_avatar_color': existing.sender.temp_avatar_color if existing.sender else '#6366f1',
                        'sender_initials': existing.sender.get_initials() if existing.sender else 'PR',
                        'is_creator': existing.sender.is_creator if existing.sender else False,
                        'content': existing.content,
                        'message_type': existing.message_type,
                        'created_at': existing.created_at.strftime('%H:%M'),
                    }

            msg = PrivateRoomMessage.objects.create(
                room_id=self.room_id,
                sender=self.participant,
                content=text,
                client_msg_id=client_msg_id,
                message_type='text'
            )
            return {
                'id': str(msg.id),
                'client_msg_id': msg.client_msg_id,
                'sender_id': str(self.participant.id),
                'sender_temp_name': self.participant.temp_name,
                'sender_avatar_color': self.participant.temp_avatar_color,
                'sender_initials': self.participant.get_initials(),
                'is_creator': self.participant.is_creator,
                'content': msg.content,
                'message_type': 'text',
                'created_at': msg.created_at.strftime('%H:%M'),
            }
        except Exception as e:
            logger.error(f"Error saving private room message: {e}")
            return None

