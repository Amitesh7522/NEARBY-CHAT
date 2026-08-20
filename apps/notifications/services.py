"""
Notifications services and real-time push.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification

class NotificationService:
    @staticmethod
    def send_notification(recipient, title, message, verb='alert', actor=None, target_type='system', target_id=''):
        """Creates a Notification record and pushes it through Channels to recipient."""
        notif = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            verb=verb,
            target_type=target_type,
            target_id=target_id,
            title=title,
            message=message,
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"user_{recipient.id}",
                {
                    'type': 'notification_event',
                    'id': str(notif.id),
                    'title': notif.title,
                    'message': notif.message,
                    'verb': notif.verb,
                    'target_type': notif.target_type,
                    'target_id': notif.target_id,
                    'created_at': notif.created_at.isoformat(),
                }
            )
        return notif
