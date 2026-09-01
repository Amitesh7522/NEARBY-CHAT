"""
Private Room Views: Landing, Room Creation, Invite Handling,
Real-Time Chat Interface, Secure Media Uploads/Streaming, and Room Management.
"""
import uuid
import secrets
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import PrivateRoom, PrivateRoomParticipant, PrivateRoomMessage
from .services import PrivateRoomService
from apps.safety.models import Report


def get_or_create_session_key(request, room_id=None):
    """
    Generates and stores a unique cryptographic session token for private room access.
    """
    if not request.session.session_key:
        request.session.create()
    
    key_name = f"private_room_session_{room_id}" if room_id else "private_session_key"
    token = request.session.get(key_name)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[key_name] = token
        request.session.modified = True
    return token


def landing_view(request):
    """
    Private Room entrance hub: Explains feature, Create CTA, and Join Code option.
    """
    return render(request, 'private_rooms/landing.html')


@login_required
def create_view(request):
    """
    Logged-in user creates a new Private Room with custom or auto-generated temp name and expiry.
    """
    if request.method == 'POST':
        duration = request.POST.get('duration', '24h')
        temp_name = request.POST.get('temp_name', '').strip()
        
        session_token = secrets.token_urlsafe(32)
        
        room, participant = PrivateRoomService.create_room(
            creator_user=request.user,
            duration_choice=duration,
            creator_temp_name=temp_name,
            session_key=session_token
        )
        
        # Save session authorization
        request.session[f"private_room_session_{room.id}"] = session_token
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


def join_code_view(request):
    """
    Allows a guest or user to join a Private Room using a 6-character short code.
    """
    if request.method == 'POST':
        join_code = request.POST.get('join_code', '').strip().upper()
        temp_name = request.POST.get('temp_name', '').strip()

        if not join_code:
            messages.error(request, _('Please enter a valid join code.'))
            return render(request, 'private_rooms/join_code.html', {
                'suggested_name': PrivateRoomService.generate_random_temp_name(),
                'join_code': join_code
            })

        room = PrivateRoom.objects.filter(join_code=join_code, is_deleted=False).first()
        if not room:
            messages.error(request, _('Invalid or expired join code. Please check and try again.'))
            return render(request, 'private_rooms/join_code.html', {
                'suggested_name': PrivateRoomService.generate_random_temp_name(),
                'join_code': join_code
            })

        if room.is_expired:
            return render(request, 'private_rooms/expired.html', {'room': room})

        session_token = request.session.get(f"private_room_session_{room.id}")
        if not session_token:
            session_token = secrets.token_urlsafe(32)
            request.session[f"private_room_session_{room.id}"] = session_token
            request.session.modified = True

        participant, status = PrivateRoomService.join_room_atomic(
            room_id_or_token=room.id,
            session_key=session_token,
            temp_name=temp_name,
            user=request.user if request.user.is_authenticated else None
        )

        if status == 'full':
            return render(request, 'private_rooms/full.html', {'room': room})
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
    """
    room = PrivateRoom.objects.filter(secure_token=secure_token, is_deleted=False).first()
    if not room:
        raise Http404(_('Private Room not found or invalid link.'))

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    # Check if already joined in this session
    session_token = request.session.get(f"private_room_session_{room.id}")
    if session_token:
        participant = PrivateRoomParticipant.objects.filter(
            room=room,
            session_key=session_token,
            is_active=True
        ).first()
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
def join_invite_view(request, secure_token):
    """
    Processes the guest acceptance of an invite and redirects to the private room chat.
    """
    room = PrivateRoom.objects.filter(secure_token=secure_token, is_deleted=False).first()
    if not room:
        raise Http404(_('Private Room not found.'))

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    temp_name = request.POST.get('temp_name', '').strip()

    session_token = request.session.get(f"private_room_session_{room.id}")
    if not session_token:
        session_token = secrets.token_urlsafe(32)
        request.session[f"private_room_session_{room.id}"] = session_token
        request.session.modified = True

    participant, status = PrivateRoomService.join_room_atomic(
        room_id_or_token=room.id,
        session_key=session_token,
        temp_name=temp_name,
        user=request.user if request.user.is_authenticated else None
    )

    if status == 'full':
        return render(request, 'private_rooms/full.html', {'room': room})
    elif status in ('expired', 'deleted'):
        return render(request, 'private_rooms/expired.html', {'room': room})

    return redirect('private_rooms:chat', room_id=room.id)


def room_chat_view(request, room_id):
    """
    Main 1-to-1 Private Room chat screen.
    """
    room = PrivateRoom.objects.filter(id=room_id).first()
    if not room:
        raise Http404(_('Private Room not found.'))

    if room.is_deleted:
        return render(request, 'private_rooms/deleted.html', {'room': room})

    if room.is_expired:
        return render(request, 'private_rooms/expired.html', {'room': room})

    session_token = request.session.get(f"private_room_session_{room_id}")
    participant = PrivateRoomParticipant.objects.filter(
        room=room,
        session_key=session_token,
        is_active=True
    ).first()

    if not participant:
        messages.error(request, _('You are not a participant of this private room.'))
        return redirect('private_rooms:landing')

    # Query other participant if present
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
def upload_media_view(request, room_id):
    """
    Secure media and file upload endpoint for Private Rooms.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    if room.is_expired or room.is_deleted:
        return JsonResponse({'success': False, 'error': 'Room is no longer active.'}, status=403)

    session_token = request.session.get(f"private_room_session_{room_id}")
    participant = PrivateRoomParticipant.objects.filter(
        room=room,
        session_key=session_token,
        is_active=True
    ).first()

    if not participant:
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
    """
    msg = get_object_or_404(PrivateRoomMessage, id=message_id)
    room = msg.room

    if room.is_deleted:
        raise Http404(_('Media is no longer available.'))

    session_token = request.session.get(f"private_room_session_{room.id}")
    participant = PrivateRoomParticipant.objects.filter(
        room=room,
        session_key=session_token,
        is_active=True
    ).first()

    if not participant:
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
def delete_room_view(request, room_id):
    """
    Creator deletes private room.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    session_token = request.session.get(f"private_room_session_{room_id}")
    participant = PrivateRoomParticipant.objects.filter(
        room=room,
        session_key=session_token,
        is_active=True
    ).first()

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
def leave_room_view(request, room_id):
    """
    Participant leaves private room.
    """
    room = get_object_or_404(PrivateRoom, id=room_id)
    session_token = request.session.get(f"private_room_session_{room_id}")
    participant = PrivateRoomParticipant.objects.filter(
        room=room,
        session_key=session_token,
        is_active=True
    ).first()

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
        if f"private_room_session_{room_id}" in request.session:
            del request.session[f"private_room_session_{room_id}"]
            request.session.modified = True

    messages.info(request, _('You have left the private room.'))
    return redirect('private_rooms:landing')


@require_POST
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

