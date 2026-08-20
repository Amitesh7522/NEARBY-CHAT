"""
Chat domain services for conversations, message persistence, and pagination.
"""
import uuid
from django.db import transaction
from django.db.models import Q, Max, Count
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from .models import Conversation, ConversationParticipant, Message, MessageStatus, ConversationRating
from apps.safety.models import Block

class ChatService:
    @staticmethod
    def get_or_create_direct_conversation(user1, user2):
        """
        Retrieves or creates a 1-on-1 direct conversation between two users.
        Checks blocking rules before initiating.
        """
        if user1 == user2:
            raise ValueError("Cannot start conversation with yourself.")

        # Check blocking
        if Block.objects.filter(
            Q(blocker=user1, blocked=user2) | Q(blocker=user2, blocked=user1)
        ).exists():
            raise PermissionDenied("Cannot start conversation due to block rules.")

        # Find existing shared direct conversation
        convs_user1 = ConversationParticipant.objects.filter(
            user=user1,
            conversation__type='direct'
        ).values_list('conversation_id', flat=True)

        shared_conv = ConversationParticipant.objects.filter(
            conversation_id__in=convs_user1,
            user=user2
        ).select_related('conversation').first()

        if shared_conv:
            return shared_conv.conversation, False

        with transaction.atomic():
            conversation = Conversation.objects.create(type='direct')
            ConversationParticipant.objects.create(conversation=conversation, user=user1)
            ConversationParticipant.objects.create(conversation=conversation, user=user2)

        return conversation, True

    @staticmethod
    def send_message(conversation_id, sender, content, client_msg_id=None, message_type='text'):
        """
        Persists a message atomically with idempotency protection.
        """
        content = content.strip()
        if not content:
            raise ValueError("Message content cannot be empty.")

        # Real-time Content Moderation & Abuse Prevention
        from apps.safety.services import ContentModerationService
        ContentModerationService.validate_or_reject(content)

        conversation = Conversation.objects.get(id=conversation_id)

        # Check if sender is participant
        if not ConversationParticipant.objects.filter(conversation=conversation, user=sender).exists():
            raise PermissionDenied("Sender is not a participant in this conversation.")

        # Check block status between participants
        other_user = conversation.get_other_participant(sender)
        if other_user and Block.objects.filter(
            Q(blocker=sender, blocked=other_user) | Q(blocker=other_user, blocked=sender)
        ).exists():
            raise PermissionDenied("Message delivery blocked.")

        # Idempotency check: if client_msg_id provided and already exists, return existing
        if client_msg_id:
            existing = Message.objects.filter(conversation=conversation, client_msg_id=client_msg_id).first()
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
                    'message_type': existing.message_type,
                    'created_at': existing.created_at.isoformat(),
                }

        with transaction.atomic():
            msg = Message.objects.create(
                conversation=conversation,
                sender=sender,
                client_msg_id=client_msg_id or str(uuid.uuid4()),
                content=content,
                message_type=message_type,
            )
            # Update conversation updated_at
            Conversation.objects.filter(id=conversation.id).update(updated_at=timezone.now())

            # Create status for other participant
            if other_user:
                MessageStatus.objects.create(
                    message=msg,
                    user=other_user,
                    status='sent'
                )

        # Trigger referral qualification and badge progression check
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
            'message_type': msg.message_type,
            'created_at': msg.created_at.isoformat(),
        }

    @staticmethod
    def get_messages_page(conversation_id, user, before_id=None, limit=25):
        """
        Fetches a page of messages for infinite scroll.
        Returns messages in chronological order.
        """
        conversation = Conversation.objects.get(id=conversation_id)
        if not ConversationParticipant.objects.filter(conversation=conversation, user=user).exists():
            raise PermissionDenied("User is not a participant.")

        qs = Message.objects.filter(conversation=conversation, is_deleted=False)
        if before_id:
            try:
                # Only filter if before_id is a valid UUID
                uuid.UUID(str(before_id))
                before_msg = Message.objects.filter(id=before_id).first()
                if before_msg:
                    qs = qs.filter(created_at__lt=before_msg.created_at)
            except (ValueError, TypeError):
                pass

        # Fetch latest N before given cursor, then order chronologically
        messages_list = list(qs.order_by('-created_at')[:limit])
        messages_list.reverse()
        return messages_list

    @staticmethod
    def mark_conversation_read(conversation_id, user):
        """
        Marks all unread messages received by user as read.
        """
        unread_statuses = MessageStatus.objects.filter(
            message__conversation_id=conversation_id,
            user=user,
            status__in=['sent', 'delivered']
        )
        updated_count = unread_statuses.update(status='read', updated_at=timezone.now())

        last_msg = Message.objects.filter(conversation_id=conversation_id).order_by('-created_at').first()
        if last_msg:
            ConversationParticipant.objects.filter(
                conversation_id=conversation_id,
                user=user
            ).update(last_read_message=last_msg)

        return updated_count

    @staticmethod
    def get_user_conversations_summary(user):
        """
        Fetches all conversations for user with last message, unread count, and other participant details.
        """
        participations = ConversationParticipant.objects.filter(
            user=user,
            conversation__is_active=True
        ).select_related('conversation').order_by('-conversation__updated_at')

        summary = []
        for p in participations:
            conv = p.conversation
            other_user = conv.get_other_participant(user)
            if not other_user:
                continue

            last_message = conv.messages.filter(is_deleted=False).order_by('-created_at').first()
            
            # Count unread messages
            unread_count = MessageStatus.objects.filter(
                message__conversation=conv,
                user=user,
                status__in=['sent', 'delivered']
            ).count()

            summary.append({
                'conversation': conv,
                'other_user': other_user,
                'other_profile': getattr(other_user, 'profile', None),
                'last_message': last_message,
                'unread_count': unread_count,
                'is_muted': p.is_muted,
                'is_archived': p.is_archived,
            })
        return summary

    @staticmethod
    def get_unrated_qualifying_conversation(rater, ratee):
        """
        Finds the most recent qualifying conversation between rater and ratee
        that has not yet been rated by rater (minimum 2 messages exchanged).
        """
        if not rater or not ratee or not rater.is_authenticated or not ratee.is_authenticated or rater == ratee:
            return None

        # Find conversations containing both participants
        rater_convs = ConversationParticipant.objects.filter(user=rater).values_list('conversation_id', flat=True)
        shared_convs = ConversationParticipant.objects.filter(
            conversation_id__in=rater_convs,
            user=ratee
        ).values_list('conversation_id', flat=True)

        if not shared_convs:
            return None

        # Find qualifying conversations with at least 2 messages
        qualifying_convs = Conversation.objects.filter(
            id__in=shared_convs,
            messages__is_deleted=False
        ).annotate(
            msg_count=Count('messages')
        ).filter(
            msg_count__gte=2
        ).order_by('-updated_at')

        # Find the first one that rater hasn't already rated
        rated_conv_ids = set(ConversationRating.objects.filter(
            conversation_id__in=shared_convs,
            rater=rater,
            ratee=ratee
        ).values_list('conversation_id', flat=True))

        for conv in qualifying_convs:
            if conv.id not in rated_conv_ids:
                return conv

        return None

    @staticmethod
    def submit_conversation_rating(conversation_id, rater, ratee, score, tags=None):
        """
        Atomically validates and saves a conversation rating.
        Enforces one rating per conversation, participant checks, and valid scores.
        """
        if not rater or not rater.is_authenticated or not ratee or not ratee.is_authenticated:
            raise PermissionDenied("Authentication required to rate.")

        if rater == ratee:
            raise ValueError("You cannot rate yourself.")

        try:
            score = int(score)
            if score < 1 or score > 5:
                raise ValueError("Score must be between 1 and 5.")
        except (TypeError, ValueError):
            raise ValueError("Invalid score provided.")

        conversation = Conversation.objects.get(id=conversation_id)

        # Verify both rater and ratee are participants
        is_rater_part = ConversationParticipant.objects.filter(conversation=conversation, user=rater).exists()
        is_ratee_part = ConversationParticipant.objects.filter(conversation=conversation, user=ratee).exists()
        if not is_rater_part or not is_ratee_part:
            raise PermissionDenied("Both users must be participants of this conversation.")

        # Verify conversation qualifies (minimum 2 messages)
        msg_count = conversation.messages.filter(is_deleted=False).count()
        if msg_count < 2:
            raise ValueError("Conversation must have at least 2 messages to be rated.")

        # Check existing rating
        if ConversationRating.objects.filter(conversation=conversation, rater=rater, ratee=ratee).exists():
            raise ValueError("You have already rated this conversation.")

        # Sanitize feedback tags
        allowed_tags = {'Friendly', 'Respectful', 'Interesting', 'Good conversation'}
        clean_tags = []
        if tags and isinstance(tags, (list, tuple)):
            for t in tags:
                t_clean = str(t).strip()
                if t_clean in allowed_tags:
                    clean_tags.append(t_clean)

        with transaction.atomic():
            rating = ConversationRating.objects.create(
                conversation=conversation,
                rater=rater,
                ratee=ratee,
                score=score,
                tags=clean_tags
            )

        return rating

    @staticmethod
    def get_user_rating_summary(user):
        """
        Calculates public rating summary and badge tags for a user.
        Only shows public rating if rating count >= 3 (threshold).
        """
        if not user or not user.is_authenticated:
            return {'show_public': False, 'rating_count': 0, 'average_score': None, 'top_tags': []}

        ratings = ConversationRating.objects.filter(ratee=user)
        count = ratings.count()

        if count < 3:
            return {
                'show_public': False,
                'rating_count': count,
                'average_score': None,
                'top_tags': [],
                'is_new_member': True,
            }

        # Calculate average
        from django.db.models import Avg
        avg_score = ratings.aggregate(Avg('score'))['score__avg'] or 0.0

        # Collect top positive tags
        tag_counts = {}
        for r in ratings:
            for t in r.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda item: -item[1])
        top_tags = [tag for tag, _ in sorted_tags[:3]]

        return {
            'show_public': True,
            'rating_count': count,
            'average_score': round(avg_score, 1),
            'top_tags': top_tags,
            'is_new_member': False,
        }
