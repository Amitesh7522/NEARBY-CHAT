"""
Global context processor providing unread counts, brand metadata, and active tab highlights.
"""
from django.db.models import Q
from apps.chat.models import MessageStatus
from apps.notifications.models import Notification

def global_context(request):
    context = {
        'APP_NAME': 'Nearby Chat',
        'APP_VERSION': '1.0.0',
        'total_unread_messages': 0,
        'total_unread_notifications': 0,
    }

    if request.user.is_authenticated:
        # Unread chat messages
        context['total_unread_messages'] = MessageStatus.objects.filter(
            user=request.user,
            status__in=['sent', 'delivered']
        ).count()

        # Unread notifications
        context['total_unread_notifications'] = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

    return context
