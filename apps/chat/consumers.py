"""
Django Channels WebSocket Consumer for Direct 1-on-1 Chats.
Provides real-time message delivery, delivery/read receipts, typing indicators, and presence updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .services import ChatService
from .models import Conversation, ConversationParticipant, Message

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"chat_{self.conversation_id}"

        # Reject unauthenticated connections
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Verify user is a member of this conversation
        is_participant = await self._is_user_participant()
        if not is_participant:
            await self.close(code=4003)
            return

        # Join conversation channel group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Mark any pending messages as read on join
        await self._mark_as_read()

        # Notify group that user is active in room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'presence_event',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'status': 'online',
            }
        )

    async def disconnect(self, close_code):
        # Leave channel group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        """
        Processes incoming WebSocket payloads from client.
        Supported actions: 'send_message', 'read_receipt', 'typing'
        """
        action = content.get('action')

        if action == 'send_message':
            text = content.get('content', '').strip()
            client_msg_id = content.get('client_msg_id', '')
            if not text:
                return

            try:
                msg_data = await database_sync_to_async(ChatService.send_message)(
                    conversation_id=self.conversation_id,
                    sender=self.user,
                    content=text,
                    client_msg_id=client_msg_id,
                    message_type='text'
                )

                # Broadcast to group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message_event',
                        'message_id': msg_data['id'],
                        'client_msg_id': msg_data['client_msg_id'],
                        'sender_id': msg_data['sender_id'],
                        'sender_username': msg_data['sender_username'],
                        'sender_name': msg_data['sender_name'],
                        'sender_avatar': msg_data['sender_avatar'],
                        'content': msg_data['content'],
                        'message_type': msg_data['message_type'],
                        'created_at': msg_data['created_at'],
                    }
                )
            except Exception as e:
                logger.error(f"Error handling send_message in ChatConsumer: {e}")
                err_text = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                await self.send_json({
                    'type': 'error',
                    'client_msg_id': client_msg_id,
                    'message': err_text
                })

        elif action == 'read_receipt':
            await self._mark_as_read()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'read_receipt_event',
                    'user_id': str(self.user.id),
                    'conversation_id': str(self.conversation_id),
                }
            )

        elif action == 'typing':
            is_typing = content.get('is_typing', False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_event',
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                    'is_typing': is_typing,
                }
            )

    # --------------------------------------------------------------------------
    # Group Event Handlers
    # --------------------------------------------------------------------------

    async def chat_message_event(self, event):
        await self.send_json({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'client_msg_id': event['client_msg_id'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'sender_name': event['sender_name'],
            'sender_avatar': event['sender_avatar'],
            'content': event['content'],
            'message_type': event['message_type'],
            'created_at': event['created_at'],
        })

    async def read_receipt_event(self, event):
        await self.send_json({
            'type': 'read_receipt',
            'user_id': event['user_id'],
            'conversation_id': event['conversation_id'],
        })

    async def typing_event(self, event):
        # Don't echo typing event back to the same user who is typing
        if event['user_id'] != str(self.user.id):
            await self.send_json({
                'type': 'typing',
                'user_id': event['user_id'],
                'username': event['username'],
                'is_typing': event['is_typing'],
            })

    async def presence_event(self, event):
        if event['user_id'] != str(self.user.id):
            await self.send_json({
                'type': 'presence',
                'user_id': event['user_id'],
                'username': event['username'],
                'status': event['status'],
            })

    # --------------------------------------------------------------------------
    # Helper DB queries
    # --------------------------------------------------------------------------

    @database_sync_to_async
    def _is_user_participant(self):
        return ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id,
            user=self.user
        ).exists()

    @database_sync_to_async
    def _mark_as_read(self):
        return ChatService.mark_conversation_read(self.conversation_id, self.user)
