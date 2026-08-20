"""
Django Channels WebSocket Consumer for Random Chat Matchmaking.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .services import MatchmakingService

logger = logging.getLogger(__name__)

class MatchingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await self.accept()

    async def disconnect(self, close_code):
        # Automatically clean up queue on socket disconnect
        if hasattr(self, 'user') and self.user.is_authenticated:
            await database_sync_to_async(MatchmakingService.cancel_queue)(self.user)

    async def receive_json(self, content):
        action = content.get('action')

        if action == 'join_queue':
            lang = content.get('language', 'any')
            mode = content.get('mode', 'interests')
            topic = content.get('interest', '')
            result = await database_sync_to_async(MatchmakingService.find_or_enqueue)(
                user=self.user,
                channel_name=self.channel_name,
                preferred_language=lang,
                mode=mode,
                topic=topic
            )

            if result.get('matched'):
                conversation_id = result['conversation_id']
                user2_channel = result['user2_channel']
                user1_name = result['user1_name']
                user1_avatar = result['user1_avatar']
                user2_name = result['user2_name']
                user2_avatar = result['user2_avatar']

                # Send match confirmation to self (User 1)
                await self.send_json({
                    'type': 'match_found',
                    'conversation_id': conversation_id,
                    'partner_name': user2_name,
                    'partner_avatar': user2_avatar,
                })

                # Send match confirmation to User 2 via channel_layer
                await self.channel_layer.send(
                    user2_channel,
                    {
                        'type': 'match_found_event',
                        'conversation_id': conversation_id,
                        'partner_name': user1_name,
                        'partner_avatar': user1_avatar,
                    }
                )
            else:
                await self.send_json({
                    'type': 'searching',
                    'message': 'Searching for nearby people...'
                })

        elif action == 'cancel_queue':
            await database_sync_to_async(MatchmakingService.cancel_queue)(self.user)
            await self.send_json({
                'type': 'queue_cancelled'
            })

    async def match_found_event(self, event):
        await self.send_json({
            'type': 'match_found',
            'conversation_id': event['conversation_id'],
            'partner_name': event['partner_name'],
            'partner_avatar': event['partner_avatar'],
        })
