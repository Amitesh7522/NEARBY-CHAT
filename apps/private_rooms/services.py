"""
Private Room Services: Temporary Name Generation, Atomic Capacity Join,
Strict Upload Security, and Room Lifecycle Management.
"""
import os
import re
import uuid
import secrets
import mimetypes
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

from .models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage


ADJECTIVES = [
    'Silver', 'Golden', 'Purple', 'Blue', 'Emerald', 'Amber', 'Cosmic',
    'Velvet', 'Quiet', 'Mystic', 'Solar', 'Lunar', 'Crimson', 'Shadow',
    'Sage', 'Ocean', 'Frost', 'Echo', 'Neon', 'Astral', 'Zenith', 'Breeze'
]

ANIMALS = [
    'Falcon', 'Owl', 'Panda', 'Fox', 'Lynx', 'Otter', 'Hawk', 'Dolphin',
    'Koala', 'Tiger', 'Badger', 'Wolf', 'Eagle', 'Stag', 'Leopard', 'Robin',
    'Raven', 'Phoenix', 'Bear', 'Sparrow', 'Seal', 'Jaguar'
]

AVATAR_COLORS = [
    '#6366f1', '#8b5cf6', '#ec4899', '#06b6d4',
    '#10b981', '#f59e0b', '#3b82f6', '#14b8a6',
    '#e11d48', '#84cc16', '#a855f7', '#0ea5e9'
]

# Security limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024       # 10 MB
MAX_AUDIO_SIZE = 25 * 1024 * 1024       # 25 MB
MAX_DOCUMENT_SIZE = 25 * 1024 * 1024    # 25 MB

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
ALLOWED_AUDIO_EXTENSIONS = {'.webm', '.ogg', '.mp3', '.m4a', '.wav', '.aac'}
ALLOWED_DOCUMENT_EXTENSIONS = {
    '.pdf', '.txt', '.docx', '.xlsx', '.pptx', '.zip', '.csv', '.rtf', '.json', '.tar', '.gz'
}

# Strictly forbidden dangerous executable and script extensions
DISALLOWED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.sh', '.bash', '.vbs', '.js', '.mjs',
    '.dll', '.msi', '.scr', '.pif', '.com', '.jar', '.apk', '.iso',
    '.bin', '.py', '.php', '.asp', '.aspx', '.jsp', '.cgi', '.pl',
    '.html', '.htm', '.xhtml', '.svg', '.hta', '.wsf', '.reg'
}


class PrivateRoomService:
    @staticmethod
    def generate_random_temp_name():
        adj = secrets.choice(ADJECTIVES)
        animal = secrets.choice(ANIMALS)
        return f"{adj} {animal}"

    @staticmethod
    def get_random_avatar_color():
        return secrets.choice(AVATAR_COLORS)

    @staticmethod
    def sanitize_temp_name(name, default="Anonymous"):
        if not name or not isinstance(name, str):
            return PrivateRoomService.generate_random_temp_name()
        # Clean special chars, trim to max 40 chars
        clean = re.sub(r'[^\w\s-]', '', name).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if len(clean) < 2:
            return PrivateRoomService.generate_random_temp_name()
        return clean[:40]

    @classmethod
    def create_room(cls, creator_user, duration_choice, creator_temp_name, session_key):
        """
        Creates a new PrivateRoom and registers the creator participant.
        """
        now = timezone.now()
        if duration_choice == '1h':
            expires_at = now + timedelta(hours=1)
        elif duration_choice == '7d':
            expires_at = now + timedelta(days=7)
        else:
            duration_choice = '24h'
            expires_at = now + timedelta(hours=24)

        # Generate unique token and join code
        secure_token = PrivateRoom.generate_secure_token()
        while PrivateRoom.objects.filter(secure_token=secure_token).exists():
            secure_token = PrivateRoom.generate_secure_token()

        join_code = PrivateRoom.generate_join_code()
        while PrivateRoom.objects.filter(join_code=join_code).exists():
            join_code = PrivateRoom.generate_join_code()

        temp_name = cls.sanitize_temp_name(creator_temp_name)
        avatar_color = cls.get_random_avatar_color()

        with transaction.atomic():
            room = PrivateRoom.objects.create(
                secure_token=secure_token,
                join_code=join_code,
                creator=creator_user if (creator_user and creator_user.is_authenticated) else None,
                creator_temp_name=temp_name,
                creator_avatar_color=avatar_color,
                duration_choice=duration_choice,
                expires_at=expires_at,
                max_participants=2
            )

            participant = PrivateRoomParticipant.objects.create(
                room=room,
                session_key=session_key,
                user=creator_user if (creator_user and creator_user.is_authenticated) else None,
                is_creator=True,
                temp_name=temp_name,
                temp_avatar_color=avatar_color
            )

            # Create initial system message
            PrivateRoomMessage.objects.create(
                room=room,
                content=f"🔒 Private Room created. Messages and shared media will expire in {room.duration_choice}.",
                message_type='system'
            )

        return room, participant

    @classmethod
    def join_room_atomic(cls, room_id_or_token, session_key, temp_name, user=None):
        """
        Atomically attempts to join a private room.
        Guarantees strict 1-to-1 capacity limit (max 2 participants).
        """
        with transaction.atomic():
            # Query with row lock
            if isinstance(room_id_or_token, uuid.UUID) or (isinstance(room_id_or_token, str) and len(room_id_or_token) == 36):
                room_qs = PrivateRoom.objects.select_for_update().filter(id=room_id_or_token)
            else:
                room_qs = PrivateRoom.objects.select_for_update().filter(secure_token=room_id_or_token)

            room = room_qs.first()
            if not room:
                return None, 'not_found'

            if room.is_deleted:
                return room, 'deleted'

            if room.is_expired:
                return room, 'expired'

            # Check if this session is already a participant
            existing_participant = PrivateRoomParticipant.objects.filter(
                room=room,
                session_key=session_key
            ).first()

            if existing_participant:
                # Update last seen
                existing_participant.last_seen_at = timezone.now()
                existing_participant.is_active = True
                existing_participant.save(update_fields=['last_seen_at', 'is_active'])
                return existing_participant, 'existing'

            # Count active participants
            active_count = PrivateRoomParticipant.objects.filter(room=room, is_active=True).count()
            if active_count >= room.max_participants:
                room.is_full = True
                room.save(update_fields=['is_full'])
                return room, 'full'

            # Pick a distinct color from existing participant
            existing_colors = set(PrivateRoomParticipant.objects.filter(room=room).values_list('temp_avatar_color', flat=True))
            available_colors = [c for c in AVATAR_COLORS if c not in existing_colors]
            avatar_color = secrets.choice(available_colors) if available_colors else cls.get_random_avatar_color()

            clean_name = cls.sanitize_temp_name(temp_name)

            participant = PrivateRoomParticipant.objects.create(
                room=room,
                session_key=session_key,
                user=user if (user and user.is_authenticated) else None,
                is_creator=False,
                temp_name=clean_name,
                temp_avatar_color=avatar_color
            )

            # Update room full status
            if active_count + 1 >= room.max_participants:
                room.is_full = True
                room.save(update_fields=['is_full'])

            # Announce join in system message
            PrivateRoomMessage.objects.create(
                room=room,
                content=f"👋 {clean_name} joined the private room.",
                message_type='system'
            )

            return participant, 'joined'

    @classmethod
    def validate_and_save_upload(cls, room, participant, file_obj, message_type):
        """
        Validates uploaded media or file with strict server-side rules and saves message.
        """
        if room.is_expired or room.is_deleted:
            raise ValidationError("This private room is no longer active.")

        if not file_obj:
            raise ValidationError("No file provided.")

        raw_name = getattr(file_obj, 'name', 'upload')
        _, ext = os.path.splitext(raw_name)
        ext = ext.lower().strip()

        # Reject disallowed/executable files
        if ext in DISALLOWED_EXTENSIONS:
            raise ValidationError(f"File type '{ext}' is not allowed for security reasons.")

        file_size = getattr(file_obj, 'size', 0)

        # Route by message type
        if message_type == 'image':
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise ValidationError("Invalid image format. Allowed: JPG, PNG, WEBP, GIF.")
            if file_size > MAX_IMAGE_SIZE:
                raise ValidationError(f"Image exceeds maximum limit of {MAX_IMAGE_SIZE // (1024*1024)} MB.")
            actual_type = 'image'
        elif message_type == 'audio':
            if ext not in ALLOWED_AUDIO_EXTENSIONS:
                # Accept .webm/.wav fallback
                ext = '.webm'
            if file_size > MAX_AUDIO_SIZE:
                raise ValidationError(f"Audio file exceeds maximum limit of {MAX_AUDIO_SIZE // (1024*1024)} MB.")
            actual_type = 'audio'
        else:
            if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
                raise ValidationError(f"File type '{ext}' is not permitted.")
            if file_size > MAX_DOCUMENT_SIZE:
                raise ValidationError(f"File exceeds maximum limit of {MAX_DOCUMENT_SIZE // (1024*1024)} MB.")
            actual_type = 'file'

        # Sanitize original filename
        safe_base = re.sub(r'[^\w.-]', '_', os.path.basename(raw_name))
        if len(safe_base) > 100:
            safe_base = safe_base[:100]

        # Generate unique storage filename
        unique_storage_name = f"{uuid.uuid4().hex}{ext}"
        file_obj.name = unique_storage_name

        mime_type = mimetypes.guess_type(raw_name)[0] or 'application/octet-stream'

        msg = PrivateRoomMessage.objects.create(
            room=room,
            sender=participant,
            message_type=actual_type,
            file=file_obj,
            file_name=safe_base,
            file_size=file_size,
            file_mime_type=mime_type,
            content=safe_base
        )

        return msg

    @classmethod
    def delete_room(cls, room, requested_by_participant):
        """
        Deletes a private room. Only creator can delete.
        Cleans up associated files.
        """
        if not requested_by_participant.is_creator:
            raise ValidationError("Only the room creator can delete this room.")

        with transaction.atomic():
            room.is_deleted = True
            room.deleted_at = timezone.now()
            room.save(update_fields=['is_deleted', 'deleted_at'])

            # Delete physical files from disk safely
            for msg in room.messages.exclude(file=''):
                if msg.file:
                    try:
                        msg.file.delete(save=False)
                    except Exception:
                        pass

            PrivateRoomMessage.objects.create(
                room=room,
                content="🚫 This private room was deleted by its creator.",
                message_type='system'
            )

        return True

    @classmethod
    def leave_room(cls, room, participant):
        """
        Marks a participant as inactive when leaving the room.
        """
        with transaction.atomic():
            participant.is_active = False
            participant.save(update_fields=['is_active'])

            PrivateRoomMessage.objects.create(
                room=room,
                content=f"🚪 {participant.temp_name} left the private room.",
                message_type='system'
            )
        return True

