"""
Private Room Models for Temporary, Anonymous, 1-to-1 Private Chat.
"""
import uuid
import secrets
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PrivateRoom(models.Model):
    """
    Temporary, strictly 1-to-1 private chat room accessible via secure token or short join code.
    """
    DURATION_CHOICES = [
        ('1h', _('1 Hour')),
        ('24h', _('24 Hours')),
        ('7d', _('7 Days')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    secure_token = models.CharField(max_length=64, unique=True, db_index=True)
    join_code = models.CharField(max_length=10, unique=True, db_index=True)
    
    # Creator FK is purely internal for audit/deletion; NEVER exposed to the guest
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_private_rooms'
    )
    creator_temp_name = models.CharField(max_length=50)
    creator_avatar_color = models.CharField(max_length=20, default='#6366f1')
    
    duration_choice = models.CharField(max_length=10, choices=DURATION_CHOICES, default='24h')
    expires_at = models.DateTimeField(db_index=True)
    is_full = models.BooleanField(default=False)
    max_participants = models.PositiveSmallIntegerField(default=2)
    
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Private Room')
        verbose_name_plural = _('Private Rooms')
        ordering = ['-created_at']

    def __str__(self):
        return f"Private Room {self.id} ({self.join_code})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def can_join(self):
        return not self.is_deleted and not self.is_expired and not self.is_full

    def time_remaining_seconds(self):
        now = timezone.now()
        if now >= self.expires_at:
            return 0
        return int((self.expires_at - now).total_seconds())

    def time_remaining_display(self):
        seconds = self.time_remaining_seconds()
        if seconds <= 0:
            return _("Expired")
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours >= 24:
            days = hours // 24
            return f"{days}d {hours % 24}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    @staticmethod
    def generate_secure_token():
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_join_code():
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(secrets.choice(alphabet) for _ in range(6))


class PrivateRoomParticipant(models.Model):
    """
    Participant in a private room.
    Scoped by a unique session secret key to ensure anonymous guest access without account creation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(PrivateRoom, on_delete=models.CASCADE, related_name='participants')
    session_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='private_participations'
    )
    is_creator = models.BooleanField(default=False)
    temp_name = models.CharField(max_length=50)
    temp_avatar_color = models.CharField(max_length=20, default='#06b6d4')
    
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Private Room Participant')
        verbose_name_plural = _('Private Room Participants')
        unique_together = ('room', 'session_key')
        indexes = [
            models.Index(fields=['room', 'session_key']),
        ]

    def __str__(self):
        return f"{self.temp_name} in Room {self.room_id}"

    def get_initials(self):
        words = self.temp_name.strip().split()
        if len(words) >= 2:
            return (words[0][0] + words[1][0]).upper()
        elif words and len(words[0]) >= 2:
            return words[0][:2].upper()
        elif words:
            return words[0][0].upper()
        return 'PR'


class PrivateRoomMessage(models.Model):
    """
    Encapsulates text, image, audio, or document messages inside a Private Room.
    """
    MESSAGE_TYPES = [
        ('text', _('Text')),
        ('image', _('Image')),
        ('file', _('File')),
        ('audio', _('Audio')),
        ('system', _('System')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(PrivateRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        PrivateRoomParticipant,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        null=True,
        blank=True
    )
    client_msg_id = models.CharField(max_length=64, db_index=True, blank=True)
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=15, choices=MESSAGE_TYPES, default='text')
    
    file = models.FileField(upload_to='private_rooms/%Y/%m/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_mime_type = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Private Room Message')
        verbose_name_plural = _('Private Room Messages')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', 'created_at']),
            models.Index(fields=['client_msg_id']),
        ]

    def __str__(self):
        sender_label = self.sender.temp_name if self.sender else 'System'
        return f"Msg {self.id} ({self.message_type}) by {sender_label}"
