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

        # Determine E2EE session state and peer public key
        state_data = await self._get_e2ee_session_state()
        time_remaining = await self._get_time_remaining()

        # Send connection established confirmation with session state and keys
        await self.send_json({
            'type': 'room_status',
            'status': 'connected',
            'session_state': state_data['session_state'],
            'time_remaining_seconds': time_remaining,
            'participant_id': str(self.participant.id),
            'participant_role': 'creator' if self.participant.is_creator else 'guest',
            'temp_name': self.participant.temp_name,
            'avatar_color': self.participant.temp_avatar_color,
            'is_creator': self.participant.is_creator,
            'my_public_key': state_data.get('my_public_key', ''),
            'peer_public_key': state_data.get('peer_public_key', ''),
            'peer_temp_name': state_data.get('peer_temp_name', ''),
            'peer_avatar_color': state_data.get('peer_avatar_color', ''),
            'peer_role': state_data.get('peer_role', ''),
        })

        # Broadcast presence and exchange public key if available
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'private_peer_online_event',
                'participant_id': str(self.participant.id),
                'sender_id': str(self.participant.id),
                'sender_role': 'creator' if self.participant.is_creator else 'guest',
                'temp_name': self.participant.temp_name,
                'avatar_color': self.participant.temp_avatar_color,
                'is_creator': self.participant.is_creator,
                'public_key': self.participant.public_key or '',
                'is_online': True,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def private_peer_online_event(self, event):
        sender_id = event.get('participant_id') or event.get('sender_id')
        if sender_id != str(self.participant.id):
            await self.send_json({
                'type': 'peer_online',
                'participant_id': sender_id,
                'sender_role': event.get('sender_role', 'guest'),
                'temp_name': event.get('temp_name', 'Partner'),
                'avatar_color': event.get('avatar_color', '#6366f1'),
                'is_creator': event.get('is_creator', False),
                'public_key': event.get('public_key', ''),
                'is_online': True,
            })

    async def private_participant_joined_event(self, event):
        sender_id = event.get('participant_id') or event.get('sender_id')
        if sender_id != str(self.participant.id):
            await self.send_json({
                'type': 'participant_joined',
                'participant_id': sender_id,
                'sender_role': event.get('sender_role', 'guest'),
                'temp_name': event.get('temp_name', 'Partner'),
                'avatar_color': event.get('avatar_color', '#6366f1'),
                'is_creator': event.get('is_creator', False),
                'public_key': event.get('public_key', ''),
                'message': event.get('message', f"👋 {event.get('temp_name', 'Partner')} joined the private room."),
            })

    async def private_peer_joined_event(self, event):
        await self.private_participant_joined_event(event)

    async def receive_json(self, content):
        """
        Handles incoming actions: 'key_exchange', 'send_message', 'typing'
        """
        action = content.get('action')

        if action == 'key_exchange':
            pub_key = content.get('public_key', '').strip()
            if not pub_key:
                await self.send_json({'type': 'error', 'message': 'Missing public key.'})
                return

            result = await self._register_public_key(pub_key)
            if not result['success']:
                await self.send_json({'type': 'error', 'message': result['error']})
                return

            if result['session_state'] == 'E2EE_ESTABLISHED':
                # Broadcast E2EE session established with both public keys
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'private_e2ee_established_event',
                        'creator_public_key': result['creator_public_key'],
                        'guest_public_key': result['guest_public_key'],
                        'session_state': 'E2EE_ESTABLISHED',
                    }
                )
            else:
                # Broadcast peer key announcement
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'private_key_announced_event',
                        'sender_id': str(self.participant.id),
                        'sender_role': 'creator' if self.participant.is_creator else 'guest',
                        'public_key': pub_key,
                        'session_state': result['session_state'],
                    }
                )

        elif action == 'send_message':
            text = content.get('content', '').strip()
            client_msg_id = content.get('client_msg_id', '')
            if not text:
                return

            if len(text) > 20000:
                await self.send_json({'type': 'error', 'message': 'Message exceeds maximum allowed ciphertext envelope size.'})
                return

            room_valid = await self._is_room_valid()
            if not room_valid:
                await self.send_json({'type': 'error', 'message': 'Room has expired or been deleted.'})
                return

            msg_data, is_new = await self._save_message(text, client_msg_id)
            if msg_data and is_new:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'private_message_event',
                        'message_id': msg_data['id'],
                        'client_msg_id': msg_data['client_msg_id'],
                        'sender_id': msg_data['sender_id'],
                        'sender_role': msg_data['sender_role'],
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
    async def private_e2ee_established_event(self, event):
        await self.send_json({
            'type': 'e2ee_established',
            'session_state': 'E2EE_ESTABLISHED',
            'creator_public_key': event['creator_public_key'],
            'guest_public_key': event['guest_public_key'],
        })

    async def private_key_announced_event(self, event):
        if event['sender_id'] != str(self.participant.id):
            await self.send_json({
                'type': 'peer_key_announced',
                'sender_id': event['sender_id'],
                'sender_role': event['sender_role'],
                'public_key': event['public_key'],
                'session_state': event['session_state'],
            })

    async def private_message_event(self, event):
        await self.send_json({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'client_msg_id': event.get('client_msg_id', ''),
            'sender_id': event['sender_id'],
            'sender_role': event.get('sender_role', 'guest'),
            'sender_temp_name': event['sender_temp_name'],
            'sender_avatar_color': event['sender_avatar_color'],
            'sender_initials': event['sender_initials'],
            'is_creator': event.get('is_creator', False),
            'content': event['content'],
            'message_type': event.get('message_type', 'text'),
            'file_url': event.get('file_url', ''),
            'file_name': event.get('file_name', ''),
            'file_size': event.get('file_size', 0),
            'encrypted_file_key': event.get('encrypted_file_key', ''),
            'file_iv': event.get('file_iv', ''),
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
    def _get_e2ee_session_state(self):
        try:
            self.participant.refresh_from_db()
            participants = list(PrivateRoomParticipant.objects.filter(
                room_id=self.room_id,
                is_active=True,
                is_blocked=False
            ))
            creator_p = next((p for p in participants if p.is_creator), None)
            guest_p = next((p for p in participants if not p.is_creator), None)

            peer = guest_p if self.participant.is_creator else creator_p

            has_both = creator_p and guest_p
            both_have_keys = has_both and bool(creator_p.public_key) and bool(guest_p.public_key)

            if both_have_keys:
                session_state = 'E2EE_ESTABLISHED'
            elif has_both:
                session_state = 'KEY_EXCHANGE'
            else:
                session_state = 'WAITING_FOR_PEER'

            return {
                'session_state': session_state,
                'my_public_key': self.participant.public_key,
                'peer_public_key': peer.public_key if peer else '',
                'peer_temp_name': peer.temp_name if peer else '',
                'peer_avatar_color': peer.temp_avatar_color if peer else '',
                'peer_role': 'guest' if self.participant.is_creator else 'creator',
                'creator_public_key': creator_p.public_key if creator_p else '',
                'guest_public_key': guest_p.public_key if guest_p else '',
            }
        except Exception as e:
            logger.error(f"Error checking E2EE session state: {e}")
            return {'session_state': 'WAITING_FOR_PEER'}

    @database_sync_to_async
    def _register_public_key(self, public_key):
        try:
            self.participant.refresh_from_db()
            participants = list(PrivateRoomParticipant.objects.filter(
                room_id=self.room_id,
                is_active=True,
                is_blocked=False
            ))
            creator_p = next((p for p in participants if p.is_creator), None)
            guest_p = next((p for p in participants if not p.is_creator), None)

            has_both = creator_p and guest_p
            both_have_keys = has_both and bool(creator_p.public_key) and bool(guest_p.public_key)

            # Immutability: reject replacement if session is established and key differs
            if both_have_keys and self.participant.public_key and self.participant.public_key != public_key:
                return {
                    'success': False,
                    'error': 'Participant public key is immutable once the encrypted session is established.'
                }

            self.participant.public_key = public_key
            self.participant.save(update_fields=['public_key'])

            if self.participant.is_creator:
                creator_p = self.participant
            else:
                guest_p = self.participant

            new_both_have_keys = creator_p and guest_p and bool(creator_p.public_key) and bool(guest_p.public_key)
            session_state = 'E2EE_ESTABLISHED' if new_both_have_keys else ('KEY_EXCHANGE' if (creator_p and guest_p) else 'WAITING_FOR_PEER')

            return {
                'success': True,
                'session_state': session_state,
                'creator_public_key': creator_p.public_key if creator_p else '',
                'guest_public_key': guest_p.public_key if guest_p else '',
            }
        except Exception as e:
            logger.error(f"Error registering public key: {e}")
            return {'success': False, 'error': str(e)}

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
                        'sender_role': 'creator' if (existing.sender and existing.sender.is_creator) else 'guest',
                        'sender_temp_name': existing.sender.temp_name if existing.sender else 'Anonymous',
                        'sender_avatar_color': existing.sender.temp_avatar_color if existing.sender else '#6366f1',
                        'sender_initials': existing.sender.get_initials() if existing.sender else 'PR',
                        'is_creator': existing.sender.is_creator if existing.sender else False,
                        'content': existing.content,
                        'message_type': existing.message_type,
                        'created_at': existing.created_at.strftime('%H:%M'),
                    }, False

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
                'sender_role': 'creator' if self.participant.is_creator else 'guest',
                'sender_temp_name': self.participant.temp_name,
                'sender_avatar_color': self.participant.temp_avatar_color,
                'sender_initials': self.participant.get_initials(),
                'is_creator': self.participant.is_creator,
                'content': msg.content,
                'message_type': 'text',
                'created_at': msg.created_at.strftime('%H:%M'),
            }, True
        except Exception as e:
            logger.error(f"Error saving private room message: {e}")
            return None, False

