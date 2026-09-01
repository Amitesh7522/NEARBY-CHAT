"""
Chat and Direct Messaging Models.
Supports direct and random 1-on-1 persistent conversations.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Conversation(models.Model):
    """
    Direct or Random 1-on-1 Conversation container.
    """
    CONVERSATION_TYPES = [
        ('direct', _('Direct Chat')),
        ('random', _('Random Chat')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=15, choices=CONVERSATION_TYPES, default='direct')
    direct_pair_key = models.CharField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Deterministic unique key for 1-on-1 conversations: min_id_max_id")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('Conversation')
        verbose_name_plural = _('Conversations')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation {self.id} ({self.type})"

    @staticmethod
    def get_pair_key(user1_id, user2_id):
        """Returns canonical deterministic pair key for two user IDs."""
        if not user1_id or not user2_id or user1_id == user2_id:
            return None
        u1_str, u2_str = str(user1_id), str(user2_id)
        return f"{min(u1_str, u2_str)}_{max(u1_str, u2_str)}"

    def get_other_participant(self, user):
        """Returns the other user participant in a 2-person conversation."""
        participant = self.participants.exclude(user=user).select_related('user', 'user__profile').first()
        return participant.user if participant else None


class ConversationParticipant(models.Model):
    """
    Participant in a conversation. Tracks per-user read states.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_participations')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_message = models.ForeignKey('Message', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    is_archived = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Conversation Participant')
        verbose_name_plural = _('Conversation Participants')
        unique_together = ('conversation', 'user')
        indexes = [
            models.Index(fields=['user', 'conversation']),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.conversation_id}"


class Message(models.Model):
    """
    Individual persistent message.
    Includes client_msg_id idempotency key to prevent duplicates during retries/network hiccups.
    """
    MESSAGE_TYPES = [
        ('text', _('Text')),
        ('image', _('Image')),
        ('system', _('System')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        null=True,
        blank=True
    )
    client_msg_id = models.CharField(max_length=64, db_index=True, blank=True)
    content = models.TextField()
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    image = models.ImageField(upload_to='chat_images/%Y/%m/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['client_msg_id']),
        ]

    def __str__(self):
        return f"Msg {self.id} by {self.sender.username if self.sender else 'System'}"


class MessageStatus(models.Model):
    """
    Delivery and Read state tracking for each recipient.
    """
    STATUS_CHOICES = [
        ('sent', _('Sent')),
        ('delivered', _('Delivered')),
        ('read', _('Read')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='statuses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_statuses')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='sent')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Message Status')
        verbose_name_plural = _('Message Statuses')
        unique_together = ('message', 'user')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['message', 'user']),
        ]

    def __str__(self):
        return f"Msg {self.message_id} -> {self.user.username}: {self.status}"


class ConversationRating(models.Model):
    """
    Stores post-conversation feedback rating between two participants.
    Strictly prevents duplicate or manipulated ratings via database unique constraint.
    """
    FEEDBACK_TAG_CHOICES = [
        ('friendly', _('Friendly')),
        ('respectful', _('Respectful')),
        ('interesting', _('Interesting')),
        ('good_conversation', _('Good conversation')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='ratings',
        db_index=True
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_ratings'
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_ratings'
    )
    score = models.PositiveSmallIntegerField()
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Conversation Rating')
        verbose_name_plural = _('Conversation Ratings')
        unique_together = ('conversation', 'rater', 'ratee')
        indexes = [
            models.Index(fields=['ratee', 'score']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Rating {self.score}★ by {self.rater.username} for {self.ratee.username}"

