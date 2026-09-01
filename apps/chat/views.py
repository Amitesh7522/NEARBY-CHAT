"""
Chat views for conversation list, private chat room, and historical message pagination API.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponseForbidden
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Conversation, ConversationParticipant, Message
from .services import ChatService
from .serializers import MessageSerializer
from apps.safety.models import Block

User = get_user_model()

@login_required
def conversation_list_view(request):
    """
    Renders the Chats section with active conversations, unread badges, and last message previews.
    """
    conversations_summary = ChatService.get_user_conversations_summary(request.user)
    return render(request, 'chat/list.html', {
        'conversations': conversations_summary,
    })


@login_required
def conversation_detail_view(request, conversation_id):
    """
    Renders the 1-on-1 private chat interface.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id, is_active=True)
    
    # Check participant membership
    if not ConversationParticipant.objects.filter(conversation=conversation, user=request.user).exists():
        messages.error(request, _('You do not have access to this conversation.'))
        return redirect('chat:list')

    other_user = conversation.get_other_participant(request.user)
    
    # Check blocking
    is_blocked = False
    if other_user:
        is_blocked = Block.objects.filter(
            blocker=request.user, blocked=other_user
        ).exists() or Block.objects.filter(
            blocker=other_user, blocked=request.user
        ).exists()

    # Load initial batch of recent messages (25 messages)
    initial_messages = ChatService.get_messages_page(conversation_id=conversation.id, user=request.user, limit=30)
    
    # Mark existing messages as read
    ChatService.mark_conversation_read(conversation_id=conversation.id, user=request.user)

    return render(request, 'chat/detail.html', {
        'conversation': conversation,
        'other_user': other_user,
        'other_profile': getattr(other_user, 'profile', None) if other_user else None,
        'initial_messages': initial_messages,
        'is_blocked': is_blocked,
    })


@login_required
def start_direct_chat_view(request, username):
    """
    Starts or opens an existing direct conversation with target user.
    """
    target_user = get_object_or_404(User, username=username)
    if target_user == request.user:
        messages.warning(request, _('You cannot start a chat with yourself.'))
        return redirect('core:home')

    try:
        conversation, created = ChatService.get_or_create_direct_conversation(request.user, target_user)
        if created:
            target_name = target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username
            ChatService.send_message(
                conversation_id=conversation.id,
                sender=request.user,
                content=f"👋 Hey {target_name}! Nice to connect with you."
            )
        return redirect('chat:detail', conversation_id=conversation.id)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('chat:list')


@login_required
def quick_connect_view(request):
    """
    Instantly connects the user with a new available person across the platform
    (prioritizing shared interests or specific topic if requested, excluding existing chat partners, blocked users, and self).
    """
    mode = request.GET.get('mode', 'interests')
    specific_interest = request.GET.get('interest', '').strip()

    # 1. Existing chat partner IDs
    user_conv_ids = ConversationParticipant.objects.filter(user=request.user).values_list('conversation_id', flat=True)
    existing_partner_ids = set(ConversationParticipant.objects.filter(
        conversation_id__in=user_conv_ids
    ).exclude(user=request.user).values_list('user_id', flat=True))

    # 2. Blocked IDs
    blocked_by_user = Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
    blocking_user = Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
    exclude_user_ids = set(list(blocked_by_user) + list(blocking_user) + list(existing_partner_ids) + [request.user.id])

    # 3. Query candidate active users
    candidates_qs = User.objects.filter(
        is_active=True,
        profile__allow_random_chat=True
    ).exclude(
        id__in=exclude_user_ids
    )

    if specific_interest:
        specific_matches = list(candidates_qs.filter(
            profile__interests__slug=specific_interest
        ).select_related('profile').prefetch_related('profile__interests')[:30])
        candidates = specific_matches if specific_matches else list(candidates_qs.select_related('profile').prefetch_related('profile__interests')[:30])
    else:
        candidates = list(candidates_qs.select_related('profile').prefetch_related('profile__interests')[:30])

    if candidates:
        my_interest_ids = set(request.user.profile.interests.values_list('id', flat=True))
        
        # Score candidates by shared interests unless mode == 'random'
        for cand in candidates:
            cand_interests = list(cand.profile.interests.all())
            cand.shared_interests = [i for i in cand_interests if i.id in my_interest_ids]
            cand.shared_count = len(cand.shared_interests)

        if mode == 'random':
            import random
            random.shuffle(candidates)
            best_match = candidates[0]
        else:
            candidates.sort(key=lambda c: (
                -c.shared_count,
                0 if c.profile.is_currently_online else 1,
                -c.last_active.timestamp() if c.last_active else 0
            ))
            best_match = candidates[0]

        conversation, created = ChatService.get_or_create_direct_conversation(request.user, best_match)
        partner_name = best_match.profile.get_display_name() if hasattr(best_match, 'profile') else best_match.username

        if created:
            # Send initial hello greeting message
            if best_match.shared_count > 0 and mode != 'random':
                top_shared = ", ".join([f"{si.emoji} {si.name}" for si in best_match.shared_interests[:2]])
                starter_text = f"👋 Hey {partner_name}! We both love {top_shared}. Nice to meet you!"
            else:
                starter_text = f"👋 Hey {partner_name}! Nice to connect with you."

            ChatService.send_message(
                conversation_id=conversation.id,
                sender=request.user,
                content=starter_text
            )

        if best_match.shared_count > 0 and mode != 'random':
            top_shared = ", ".join([f"{si.emoji} {si.name}" for si in best_match.shared_interests[:2]])
            messages.success(request, _('Connected with %(name)s! You both love %(interests)s.') % {'name': partner_name, 'interests': top_shared})
        else:
            messages.success(request, _('Connected with %(name)s! Say hello.') % {'name': partner_name})

        return redirect('chat:detail', conversation_id=conversation.id)
    else:
        messages.info(request, _("You've connected with everyone available right now! Check back soon or explore Rooms."))
        return redirect('chat:list')


@login_required
def submit_rating_view(request):
    """
    Submits a conversation rating for a user's partner.
    Supports both AJAX requests and standard HTML form POSTs.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required.'}, status=405)

    conversation_id = request.POST.get('conversation_id')
    target_username = request.POST.get('target_username')
    score = request.POST.get('score')
    tags = request.POST.getlist('tags')

    target_user = get_object_or_404(User, username=target_username)

    try:
        rating = ChatService.submit_conversation_rating(
            conversation_id=conversation_id,
            rater=request.user,
            ratee=target_user,
            score=score,
            tags=tags
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or (request.content_type and 'application/json' in request.content_type.lower()):
            return JsonResponse({'success': True, 'message': str(_('Rating submitted. Thank you!'))})
        messages.success(request, _('Thank you for rating your conversation!'))
        return redirect('accounts:user_profile', username=target_username)
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or (request.content_type and 'application/json' in request.content_type.lower()):
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        messages.error(request, str(e))
        return redirect('accounts:user_profile', username=target_username)


# ==============================================================================
# REST API for Infinite Scroll Pagination
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def messages_api(request, conversation_id):
    """
    Loads historical messages before a given cursor message ID for smooth infinite upward scrolling.
    """
    before_id = request.GET.get('before_id')
    try:
        messages_list = ChatService.get_messages_page(
            conversation_id=conversation_id,
            user=request.user,
            before_id=before_id,
            limit=25
        )
        serializer = MessageSerializer(messages_list, many=True)
        has_more = len(messages_list) == 25
        return Response({
            'messages': serializer.data,
            'has_more': has_more,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)
