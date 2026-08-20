"""
Random Chat Matching Engine Services.
Provides atomic matchmaking, concurrency safety, block exclusion, and timeout cleanup.
"""
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import MatchQueue
from apps.chat.models import Conversation, ConversationParticipant
from apps.chat.services import ChatService
from apps.safety.models import Block

class MatchmakingService:
    @staticmethod
    def find_or_enqueue(user, channel_name, preferred_language='any', mode='interests', topic=''):
        """
        Attempts to match the user with an eligible waiting user immediately.
        Prioritizes shared interests or topic when specified.
        If an eligible partner is found, creates a random Conversation atomically.
        Otherwise, enqueues the user into MatchQueue.
        """
        # Cleanup any stale entries older than 2 minutes
        MatchmakingService.cleanup_stale()

        # Gather blocked user IDs to exclude
        blocked_by_user = Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)
        blocking_user = Block.objects.filter(blocked=user).values_list('blocker_id', flat=True)

        # Gather existing conversation partners to strictly exclude from random chat
        user_conv_ids = ConversationParticipant.objects.filter(user=user).values_list('conversation_id', flat=True)
        existing_partner_ids = set(ConversationParticipant.objects.filter(
            conversation_id__in=user_conv_ids
        ).exclude(user=user).values_list('user_id', flat=True))

        exclude_user_ids = set(list(blocked_by_user) + list(blocking_user) + list(existing_partner_ids) + [user.id])

        with transaction.atomic():
            # Query candidate queue entries
            queue_qs = MatchQueue.objects.select_for_update(skip_locked=True).filter(
                status='waiting'
            ).exclude(
                user_id__in=exclude_user_ids
            )

            # If specific topic requested, try finding candidate with this topic or interest
            candidate_queue = None
            if topic:
                candidate_queue = queue_qs.filter(user__profile__interests__slug=topic).order_by('queued_at').first()

            # If not found or mode == 'interests', try finding candidate with any shared interest
            if not candidate_queue and mode == 'interests':
                my_interest_ids = user.profile.interests.values_list('id', flat=True)
                if my_interest_ids:
                    candidate_queue = queue_qs.filter(user__profile__interests__in=my_interest_ids).order_by('queued_at').first()

            # Fall back to any waiting candidate
            if not candidate_queue:
                candidate_queue = queue_qs.order_by('queued_at').first()

            if candidate_queue:
                partner_user = candidate_queue.user
                partner_channel = candidate_queue.channel_name

                # Create brand new random conversation
                conv = Conversation.objects.create(type='random')
                ConversationParticipant.objects.create(conversation=conv, user=user)
                ConversationParticipant.objects.create(conversation=conv, user=partner_user)

                # Remove candidate from queue and delete any existing queue entry for this user
                candidate_queue.delete()
                MatchQueue.objects.filter(user=user).delete()

                user1_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username
                user1_avatar = user.profile.get_avatar_url() if hasattr(user, 'profile') else '/static/images/default-avatar.svg'

                user2_name = partner_user.profile.get_display_name() if hasattr(partner_user, 'profile') else partner_user.username
                user2_avatar = partner_user.profile.get_avatar_url() if hasattr(partner_user, 'profile') else '/static/images/default-avatar.svg'

                # Send initial hello greeting from user to partner_user
                if topic:
                    starter_content = f"👋 Hey {user2_name}! We matched on #{topic} via Nearby Chat."
                else:
                    starter_content = f"👋 Hey {user2_name}! We just matched on Nearby Chat."

                ChatService.send_message(
                    conversation_id=conv.id,
                    sender=user,
                    content=starter_content
                )

                return {
                    'matched': True,
                    'conversation_id': str(conv.id),
                    'user1_channel': channel_name,
                    'user1_name': user1_name,
                    'user1_avatar': user1_avatar,
                    'user2_channel': partner_channel,
                    'user2_name': user2_name,
                    'user2_avatar': user2_avatar,
                }
            else:
                # No partner found right now, upsert this user into queue
                MatchQueue.objects.update_or_create(
                    user=user,
                    defaults={
                        'channel_name': channel_name,
                        'preferred_language': preferred_language,
                        'status': 'waiting',
                        'queued_at': timezone.now(),
                    }
                )
                return {'matched': False}

    @staticmethod
    def cancel_queue(user):
        """Cancels user waiting entry in matchmaking queue."""
        MatchQueue.objects.filter(user=user).delete()

    @staticmethod
    def cleanup_stale(timeout_seconds=120):
        """Removes orphaned queue entries older than timeout_seconds."""
        cutoff = timezone.now() - timedelta(seconds=timeout_seconds)
        MatchQueue.objects.filter(queued_at__lt=cutoff).delete()
