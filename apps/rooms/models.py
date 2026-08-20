"""
Community Rooms and Group Messaging Models.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

class Room(models.Model):
    """
    Public and Topic-based Community Rooms.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_('Room Name'), max_length=80)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    topic = models.CharField(_('Topic / Category'), max_length=50, blank=True)
    description = models.TextField(_('Description'), max_length=400, blank=True)
    avatar = models.ImageField(_('Room Icon'), upload_to='room_avatars/%Y/%m/', blank=True, null=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_rooms')
    is_public = models.BooleanField(_('Public Room'), default=True)
    max_members = models.PositiveIntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Room')
        verbose_name_plural = _('Rooms')
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or str(uuid.uuid4())[:8]
            slug = base_slug
            counter = 1
            while Room.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return '/static/images/default-room.svg'

    @property
    def member_count(self):
        return self.members.count()


class RoomMember(models.Model):
    """
    Tracks room membership and administrative roles.
    """
    ROLE_CHOICES = [
        ('owner', _('Owner')),
        ('admin', _('Admin')),
        ('member', _('Member')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_memberships')
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Room Member')
        verbose_name_plural = _('Room Members')
        unique_together = ('room', 'user')
        indexes = [
            models.Index(fields=['room', 'user']),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.room.name} ({self.role})"


class RoomMessage(models.Model):
    """
    Persistent message posted to a community room.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='room_messages',
        null=True,
        blank=True
    )
    client_msg_id = models.CharField(max_length=64, db_index=True, blank=True)
    content = models.TextField()
    message_type = models.CharField(max_length=10, default='text')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Room Message')
        verbose_name_plural = _('Room Messages')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', 'created_at']),
        ]

    def __str__(self):
        return f"RoomMsg in {self.room.name} by {self.sender.username if self.sender else 'System'}"
