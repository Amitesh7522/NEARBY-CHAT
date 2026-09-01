"""
Django Channels WebSocket Consumer for User Notifications and Presence.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from apps.accounts.models import Profile

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        from apps.core.security import validate_websocket_origin
        if not validate_websocket_origin(self.scope):
            await self.close(code=4003)
            return

        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        await self.accept()

        # Update online status
        await self._set_online_status(True)

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        if hasattr(self, 'user') and self.user.is_authenticated:
            await self._set_online_status(False)

    async def notification_event(self, event):
        await self.send_json({
            'type': 'notification',
            'id': event['id'],
            'title': event['title'],
            'message': event['message'],
            'verb': event['verb'],
            'target_type': event['target_type'],
            'target_id': event['target_id'],
            'created_at': event['created_at'],
        })

    @database_sync_to_async
    def _set_online_status(self, is_online):
        if hasattr(self.user, 'profile'):
            Profile.objects.filter(id=self.user.profile.id).update(
                is_online=is_online,
                last_seen=timezone.now()
            )
