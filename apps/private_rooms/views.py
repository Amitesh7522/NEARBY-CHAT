"""
Private Room Views: Landing, Room Creation, Invite Handling,
Real-Time Chat Interface, Rate-Limited Join Lookups, Secure Media Uploads/Streaming,
and Room Lifecycle Management (Leave, Delete, Block, Report).
"""
import uuid
import secrets
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from .services import PrivateRoomService, hash_token
from apps.safety.models import Report


def is_rate_limited(request, action='join_code', limit=5, window=60):
    """
    Cache-based IP/session rate limiter to prevent join code brute force.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')

    cache_key = f"pr_rate_{action}_{ip}"
    count = cache.get(cache_key, 0)
    if count >= limit:
        return True
    cache.set(cache_key, count + 1, window)
    return False


def get_participant_from_session(request, room):
    """
    Retrieves and validates the active PrivateRoomParticipant using the hashed session credential.
    """
    raw_token = (
        request.session.get(f"pr_auth_{room.id}") or
        request.session.get(f"private_room_session_{room.id}") or
        request.session.get("private_session_key")
    )
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    return PrivateRoomParticipant.objects.filter(
        room=room,
        session_token_hash=token_hash,
        is_active=True
    ).first()


def get_user_active_private_rooms(request):
    """
    Returns list of active, unexpired, non-deleted, non-blocked private room participants
    for the current user (if logged in) or the current session.
    """
    now = timezone.now()
    active_participations = []
    seen_room_ids = set()

    # 1. Check logged-in user
    if request.user.is_authenticated:
        user_parts = PrivateRoomParticipant.objects.filter(
            user=request.user,
            is_active=True,
            is_blocked=False,
            room__is_deleted=False,
            room__is_blocked=False,
            room__expires_at__gt=now
        ).select_related('room').order_by('-room__created_at')
        for p in user_parts:
            if p.room.id not in seen_room_ids:
                seen_room_ids.add(p.room.id)
                active_participations.append(p)

    # 2. Check room-scoped session tokens (for guests or creator sessions)
    for key, raw_token in list(request.session.items()):
        if key.startswith('pr_auth_') or key.startswith('private_room_session_'):
            room_id_str = key.replace('pr_auth_', '').replace('private_room_session_', '')
            try:
                room_uuid = uuid.UUID(room_id_str)
            except (ValueError, AttributeError):
                continue
            if room_uuid in seen_room_ids:
                continue

            token_hash = hash_token(raw_token)
            p = PrivateRoomParticipant.objects.filter(
                room_id=room_uuid,
                session_token_hash=token_hash,
                is_active=True,
                is_blocked=False,
                room__is_deleted=False,
                room__is_blocked=False,
                room__expires_at__gt=now
            ).select_related('room').first()
            if p and p.room.id not in seen_room_ids:
                seen_room_ids.add(p.room.id)
                active_participations.append(p)

    return active_participations


def landing_view(request):
    """
    Private Room entrance hub: Explains feature, displays active resumable rooms,
    Create CTA, and Join Code option.
    """
    active_participations = get_user_active_private_rooms(request)
    return render(request, 'private_rooms/landing.html', {
        'active_participations': active_participations,
    })


@login_required
@csrf_protect
def create_view(request):
    """
    Logged-in user creates a new Private Room with custom or auto-generated temp name and expiry.
    """
    if request.method == 'POST':
        duration = request.POST.get('duration', '24h')
        temp_name = request.POST.get('temp_name', '').strip()
        
        # Raw session token stored in client session cookie only
        raw_session_token = secrets.token_urlsafe(32)
        
        room, participant = PrivateRoomService.create_room(
            creator_user=request.user,
            duration_choice=duration,
            creator_temp_name=temp_name,
            raw_session_token=raw_session_token
        )
        
        # Save raw token in session cookie (scoped to room)
        request.session[f"pr_auth_{room.id}"] = raw_session_token
        request.session.modified = True
        
        return redirect('private_rooms:created_share', secure_token=room.secure_token)

    suggested_name = PrivateRoomService.generate_random_temp_name()
    return render(request, 'private_rooms/create.html', {
        'suggested_name': suggested_name,
    })


def created_share_view(request, secure_token):
    """
    Displays the secure invite link, join code, and share actions after room creation.
    """
    room = get_object_or_404(PrivateRoom, secure_token=secure_token, is_deleted=False)
    
    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    invite_url = request.build_absolute_uri(
        reverse('private_rooms:invite_landing', kwargs={'secure_token': room.secure_token})
    )

    return render(request, 'private_rooms/created.html', {
        'room': room,
        'invite_url': invite_url,
    })


@csrf_protect
def join_code_view(request):
    """
    Allows a guest or user to join a Private Room using a 6-character short code.
    Enforces rate limiting to prevent brute-force attacks.
    """
    if request.method == 'POST':
        if is_rate_limited(request, action='join_code', limit=6, window=60):
            messages.error(request, _('Too many attempts. Please wait a minute before trying another join code.'))
            return render(request, 'private_rooms/join_code.html', {
                'suggested_name': PrivateRoomService.generate_random_temp_name(),
                'join_code': request.POST.get('join_code', '').strip().upper()
            })

        join_code = request.POST.get('join_code', '').strip().upper()
        temp_name = request.POST.get('temp_name', '').strip()

        if not join_code:
            messages.error(request, _('Please enter a valid join code.'))
            return render(request, 'private_rooms/join_code.html', {
                'suggested_name': PrivateRoomService.generate_random_temp_name(),
                'join_code': join_code
            })

        # Only look up non-deleted, non-blocked, active rooms
        room = PrivateRoom.objects.filter(
            join_code=join_code,
            is_deleted=False,
            is_blocked=False,
            expires_at__gt=timezone.now()
        ).first()

        if not room:
            messages.error(request, _('Invalid or expired join code. Please check and try again.'))
            return render(request, 'private_rooms/join_code.html', {
                'suggested_name': PrivateRoomService.generate_random_temp_name(),
                'join_code': join_code
            })

        raw_session_token = request.session.get(f"pr_auth_{room.id}")
        if not raw_session_token:
            raw_session_token = secrets.token_urlsafe(32)
            request.session[f"pr_auth_{room.id}"] = raw_session_token
            request.session.modified = True

        participant, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            raw_session_token=raw_session_token,
            temp_name=temp_name,
            user=request.user if request.user.is_authenticated else None
        )

        if status == 'full':
            return render(request, 'private_rooms/full.html', {'room': room})
        elif status == 'blocked':
            return render(request, 'private_rooms/deleted.html', {'room': room})
        elif status in ('expired', 'deleted'):
            return render(request, 'private_rooms/expired.html', {'room': room})

        return redirect('private_rooms:chat', room_id=room.id)

    suggested_name = PrivateRoomService.generate_random_temp_name()
    initial_code = request.GET.get('code', '').strip().upper()
    return render(request, 'private_rooms/join_code.html', {
        'suggested_name': suggested_name,
        'join_code': initial_code,
    })


def invite_landing_view(request, secure_token):
    """
    Guest landing page for secure invite URLs.
    Supports seamless re-entry for existing participants.
    """
    room = PrivateRoom.objects.filter(secure_token=secure_token, is_deleted=False).first()
    if not room:
        raise Http404(_('Private Room not found or invalid link.'))

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    if room.is_blocked:
        return render(request, 'private_rooms/deleted.html', {'room': room})

    # Check for existing participant session (seamless re-entry)
    participant = get_participant_from_session(request, room)
    if participant:
        return redirect('private_rooms:chat', room_id=room.id)

    if room.is_full:
        return render(request, 'private_rooms/full.html', {'room': room})

    suggested_name = PrivateRoomService.generate_random_temp_name()
    return render(request, 'private_rooms/invite.html', {
        'room': room,
        'suggested_name': suggested_name,
    })


@require_POST
@csrf_protect
def join_invite_view(request, secure_token):
    """
    Processes the guest acceptance of an invite and redirects to the private room chat.
    """
    room = PrivateRoom.objects.filter(secure_token=secure_token, is_deleted=False).first()
    if not room:
        raise Http404(_('Private Room not found.'))

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    if room.is_blocked:
        return render(request, 'private_rooms/deleted.html', {'room': room})

    temp_name = request.POST.get('temp_name', '').strip()

    raw_session_token = request.session.get(f"pr_auth_{room.id}")
    if not raw_session_token:
        raw_session_token = secrets.token_urlsafe(32)
        request.session[f"pr_auth_{room.id}"] = raw_session_token
        request.session.modified = True

    participant, status = PrivateRoomService.join_room_atomic(
        room_id_or_token=room.id,
        raw_session_token=raw_session_token,
        temp_name=temp_name,
        user=request.user if request.user.is_authenticated else None
    )

    if status == 'full':
        return render(request, 'private_rooms/full.html', {'room': room})
    elif status == 'blocked':
        return render(request, 'private_rooms/deleted.html', {'room': room})
    elif status in ('expired', 'deleted'):
        return render(request, 'private_rooms/expired.html', {'room': room})

    return redirect('private_rooms:chat', room_id=room.id)


def room_chat_view(request, room_id):
    """
    Main 1-to-1 Private Room chat screen.
    Ensures zero identity leakage, authenticated participation, and live re-entry.
    """
    room = PrivateRoom.objects.filter(id=room_id).first()
    if not room:
        raise Http404(_('Private Room not found.'))

    if room.is_deleted:
        return render(request, 'private_rooms/deleted.html', {'room': room})

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    if room.is_blocked:
        return render(request, 'private_rooms/deleted.html', {'room': room})

    participant = get_participant_from_session(request, room)
    if not participant:
        messages.error(request, _('You are not a participant of this private room.'))
        return redirect('private_rooms:landing')

    # Query other participant if present (strictly anonymous representation)
    other_participant = room.participants.filter(is_active=True).exclude(id=participant.id).first()

    # Load initial messages
    initial_messages = room.messages.select_related('sender').order_by('created_at')[:50]

    return render(request, 'private_rooms/chat.html', {
        'room': room,
        'current_participant': participant,
        'other_participant': other_participant,
        'initial_messages': initial_messages,
        'time_remaining_seconds': room.time_remaining_seconds(),
        'time_remaining_display': room.time_remaining_display(),
    })


@require_POST
@csrf_protect
def upload_media_view(request, room_id):
    """
    Secure media and file upload endpoint for Private Rooms.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    if room.is_expired or room.is_deleted or room.is_blocked:
        return JsonResponse({'success': False, 'error': 'Room is no longer active.'}, status=403)

    participant = get_participant_from_session(request, room)
    if not participant or participant.is_blocked:
        return JsonResponse({'success': False, 'error': 'Unauthorized.'}, status=403)

    file_obj = request.FILES.get('file')
    message_type = request.POST.get('message_type', 'file')

    try:
        msg = PrivateRoomService.validate_and_save_upload(
            room=room,
            participant=participant,
            file_obj=file_obj,
            message_type=message_type
        )

        media_url = reverse('private_rooms:serve_media', kwargs={'message_id': msg.id})

        # Broadcast message via WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"private_room_{room.id}",
                {
                    'type': 'private_message_event',
                    'message_id': str(msg.id),
                    'sender_id': str(participant.id),
                    'sender_temp_name': participant.temp_name,
                    'sender_avatar_color': participant.temp_avatar_color,
                    'sender_initials': participant.get_initials(),
                    'is_creator': participant.is_creator,
                    'content': msg.content,
                    'message_type': msg.message_type,
                    'file_url': media_url,
                    'file_name': msg.file_name,
                    'file_size': msg.file_size,
                    'created_at': msg.created_at.strftime('%H:%M'),
                }
            )

        return JsonResponse({
            'success': True,
            'message_id': str(msg.id),
            'file_url': media_url,
            'file_name': msg.file_name,
            'file_size': msg.file_size,
            'message_type': msg.message_type,
            'created_at': msg.created_at.strftime('%H:%M'),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def serve_media_view(request, message_id):
    """
    Streams private media only to verified room participants.
    Validates hashed session credentials against active room participants.
    """
    msg = get_object_or_404(PrivateRoomMessage, id=message_id)
    room = msg.room

    if room.is_deleted or room.is_expired or room.is_blocked:
        raise Http404(_('Media is no longer available.'))

    participant = get_participant_from_session(request, room)
    if not participant or participant.is_blocked:
        return HttpResponseForbidden(_('Access denied to private media.'))

    if not msg.file or not msg.file.name:
        raise Http404(_('File not found.'))

    try:
        response = FileResponse(msg.file.open('rb'), content_type=msg.file_mime_type or 'application/octet-stream')
        # If document, trigger download with safe original name
        if msg.message_type == 'file':
            response['Content-Disposition'] = f'attachment; filename="{msg.file_name}"'
        return response
    except FileNotFoundError:
        raise Http404(_('File not found on server.'))


@require_POST
@csrf_protect
def delete_room_view(request, room_id):
    """
    Creator deletes private room.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    participant = get_participant_from_session(request, room)

    if not participant or not participant.is_creator:
        messages.error(request, _('Only the room creator can delete this room.'))
        return redirect('private_rooms:chat', room_id=room_id)

    PrivateRoomService.delete_room(room, participant)

    # Notify WebSocket group
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"private_room_{room.id}",
            {
                'type': 'private_system_event',
                'event': 'deleted',
                'message': str(_('This private room was deleted by its creator.')),
            }
        )

    messages.success(request, _('Private Room deleted successfully.'))
    return redirect('private_rooms:landing')


@require_POST
@csrf_protect
def leave_room_view(request, room_id):
    """
    Participant leaves private room.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    participant = get_participant_from_session(request, room)

    if participant:
        PrivateRoomService.leave_room(room, participant)
        
        # Notify WebSocket group
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"private_room_{room.id}",
                {
                    'type': 'private_system_event',
                    'event': 'participant_left',
                    'message': f"{participant.temp_name} left the room.",
                }
            )

        # Clear session
        if f"pr_auth_{room_id}" in request.session:
            del request.session[f"pr_auth_{room_id}"]
            request.session.modified = True

    messages.info(request, _('You have left the private room.'))
    return redirect('private_rooms:landing')


@require_POST
@csrf_protect
def block_room_view(request, room_id):
    """
    V1 Block behavior: Terminates further interaction between the two participants
    without exposing either participant's NearbyChat identity.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    participant = get_participant_from_session(request, room)

    if participant:
        PrivateRoomService.block_room(room, participant)

        # Notify WebSocket group
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"private_room_{room.id}",
                {
                    'type': 'private_system_event',
                    'event': 'blocked',
                    'message': str(_('This private room session has been blocked.')),
                }
            )

        if f"pr_auth_{room_id}" in request.session:
            del request.session[f"pr_auth_{room_id}"]
            request.session.modified = True

    messages.info(request, _('Private room blocked.'))
    return redirect('private_rooms:landing')


@require_POST
@csrf_protect
def report_room_view(request, room_id):
    """
    Files an anonymous safety report for a private room.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    reason = request.POST.get('reason', 'other')
    details = request.POST.get('details', '').strip()

    Report.objects.create(
        reporter=request.user if request.user.is_authenticated else None,
        reason=reason,
        details=f"[Private Room {room.id} - JoinCode {room.join_code}] {details}"
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': str(_('Report submitted. Thank you.'))})

    messages.success(request, _('Your report has been received by our safety team.'))
    return redirect('private_rooms:chat', room_id=room.id)


