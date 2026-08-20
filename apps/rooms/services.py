"""
Rooms domain services for room management, memberships, and room messaging.
"""
import uuid
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .models import Room, RoomMember, RoomMessage

class RoomService:
    @staticmethod
    def create_room(creator, name, topic='', description='', avatar=None, is_public=True):
        """Creates a new room and automatically assigns creator as owner."""
        with transaction.atomic():
            room = Room.objects.create(
                name=name,
                topic=topic,
                description=description,
                avatar=avatar,
                creator=creator,
                is_public=is_public,
            )
            RoomMember.objects.create(
                room=room,
                user=creator,
                role='owner'
            )
        return room

    @staticmethod
    def join_room(user, room):
        """Adds user to room members if capacity allows."""
        if room.members.count() >= room.max_members:
            raise ValueError("Room is at maximum capacity.")
        
        member, created = RoomMember.objects.get_or_create(
            room=room,
            user=user,
            defaults={'role': 'member'}
        )
        return member, created

    @staticmethod
    def leave_room(user, room):
        """Removes user from room members."""
        RoomMember.objects.filter(room=room, user=user).delete()

    @staticmethod
    def send_room_message(room_id, sender, content, client_msg_id=None):
        """Persists a room message atomically."""
        content = content.strip()
        if not content:
            raise ValueError("Message cannot be empty.")

        # Real-time Content Moderation & Abuse Prevention
        from apps.safety.services import ContentModerationService
        ContentModerationService.validate_or_reject(content)

        room = Room.objects.get(id=room_id)
        
        # Check membership
        if not RoomMember.objects.filter(room=room, user=sender).exists():
            raise PermissionDenied("You must join the room before sending messages.")

        # Idempotency check
        if client_msg_id:
            existing = RoomMessage.objects.filter(room=room, client_msg_id=client_msg_id).first()
            if existing:
                s_name = sender.profile.get_display_name() if hasattr(sender, 'profile') else sender.username
                s_avatar = sender.profile.get_avatar_url() if hasattr(sender, 'profile') else '/static/images/default-avatar.svg'
                return {
                    'id': str(existing.id),
                    'client_msg_id': existing.client_msg_id,
                    'sender_id': str(sender.id),
                    'sender_username': sender.username,
                    'sender_name': s_name,
                    'sender_avatar': s_avatar,
                    'content': existing.content,
                    'created_at': existing.created_at.isoformat(),
                }

        with transaction.atomic():
            msg = RoomMessage.objects.create(
                room=room,
                sender=sender,
                client_msg_id=client_msg_id or str(uuid.uuid4()),
                content=content,
            )
            Room.objects.filter(id=room.id).update(updated_at=timezone.now())

        # Trigger referral qualification check
        try:
            from apps.accounts.services import ReferralService
            ReferralService.check_and_qualify_referral(sender)
        except Exception:
            pass

        sender_name = sender.profile.get_display_name() if hasattr(sender, 'profile') else sender.username
        sender_avatar = sender.profile.get_avatar_url() if hasattr(sender, 'profile') else '/static/images/default-avatar.svg'

        return {
            'id': str(msg.id),
            'client_msg_id': msg.client_msg_id,
            'sender_id': str(sender.id),
            'sender_username': sender.username,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
        }

    @staticmethod
    def get_room_messages(room_id, limit=40):
        """Returns the latest messages for a room ordered chronologically."""
        qs = RoomMessage.objects.filter(
            room_id=room_id,
            is_deleted=False
        ).select_related('sender', 'sender__profile').order_by('-created_at')[:limit]
        messages_list = list(qs)
        messages_list.reverse()
        return messages_list
