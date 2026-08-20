"""
Random Chat Matching Queue Models.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class MatchQueue(models.Model):
    """
    Real-time matchmaking waiting queue.
    """
    STATUS_CHOICES = [
        ('waiting', _('Waiting')),
        ('matched', _('Matched')),
        ('cancelled', _('Cancelled')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='match_queue_entry'
    )
    channel_name = models.CharField(max_length=255)
    preferred_language = models.CharField(max_length=10, default='any')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='waiting', db_index=True)
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Match Queue Entry')
        verbose_name_plural = _('Match Queue Entries')
        indexes = [
            models.Index(fields=['status', 'queued_at']),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.status}) - {self.queued_at}"
