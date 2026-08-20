"""
User Notifications Model.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Notification(models.Model):
    TARGET_TYPE_CHOICES = [
        ('chat', _('Chat Message')),
        ('room', _('Room Activity')),
        ('match', _('Random Match')),
        ('safety', _('Safety / Moderation')),
        ('system', _('System Announcement')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_notifications'
    )
    verb = models.CharField(max_length=60)
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES, default='system')
    target_id = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
        ]

    def __str__(self):
        return f"Notif to {self.recipient.username}: {self.title}"


class WebPushSubscription(models.Model):
    """
    Stores browser Web Push endpoint and cryptographic keys for a user device.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_subscriptions'
    )
    endpoint = models.TextField(unique=True, db_index=True)
    p256dh = models.CharField(max_length=255, blank=True)
    auth = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Web Push Subscription')
        verbose_name_plural = _('Web Push Subscriptions')

    def __str__(self):
        return f"Push Subscription ({self.user.username})"

