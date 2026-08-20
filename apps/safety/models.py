"""
Safety Models: User Blocking, Content/User Reporting, and Admin Moderation Actions.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class Block(models.Model):
    """
    Bidirectional safety block. Blocker prevents interactions from Blocked.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocked_users'
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocked_by_users'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Block')
        verbose_name_plural = _('Blocks')
        unique_together = ('blocker', 'blocked')
        indexes = [
            models.Index(fields=['blocker', 'blocked']),
        ]

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"


class Report(models.Model):
    """
    User-submitted reports on abusive users, inappropriate messages, or rooms.
    """
    REASON_CHOICES = [
        ('harassment', _('Harassment or Bullying')),
        ('hate_speech', _('Hate Speech or Discrimination')),
        ('spam', _('Spam or Scam')),
        ('inappropriate_content', _('Nudity or Inappropriate Content')),
        ('violence', _('Threat of Violence or Self-Harm')),
        ('impersonation', _('Impersonation')),
        ('other', _('Other Violation')),
    ]

    STATUS_CHOICES = [
        ('pending', _('Pending Review')),
        ('investigating', _('Under Investigation')),
        ('resolved', _('Action Taken (Resolved)')),
        ('dismissed', _('Dismissed (No Violation)')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_reports'
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports_received'
    )
    reported_room = models.ForeignKey(
        'rooms.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    reported_message = models.ForeignKey(
        'chat.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default='harassment')
    details = models.TextField(_('Details / Explanation'), max_length=1000, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    
    # Internal Moderation
    moderator_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Report')
        verbose_name_plural = _('Reports')
        ordering = ['-created_at']

    def __str__(self):
        return f"Report #{str(self.id)[:8]} by {self.reporter.username} ({self.status})"


class ModerationAction(models.Model):
    """
    Internal administrative actions taken on malicious accounts.
    """
    ACTION_CHOICES = [
        ('warning', _('Official Warning')),
        ('temp_suspension', _('Temporary Suspension')),
        ('permanent_ban', _('Permanent Ban')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='moderation_history'
    )
    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='issued_moderation_actions'
    )
    action_type = models.CharField(max_length=25, choices=ACTION_CHOICES, default='warning')
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Moderation Action')
        verbose_name_plural = _('Moderation Actions')

    def __str__(self):
        return f"{self.action_type} for {self.user.username}"
