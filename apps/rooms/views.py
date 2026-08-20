"""
Rooms views for browsing, creating, joining, and messaging in rooms.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from .models import Room, RoomMember
from .forms import RoomForm
from .services import RoomService

@login_required
def room_list_view(request):
    """
    Renders the Rooms section with public rooms, category filters, and user joined rooms.
    """
    query = request.GET.get('q', '').strip()
    topic = request.GET.get('topic', '').strip()

    rooms_qs = Room.objects.filter(is_public=True).select_related('creator')
    if query:
        rooms_qs = rooms_qs.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(topic__icontains=query))
    if topic:
        rooms_qs = rooms_qs.filter(topic__iexact=topic)

    my_room_ids = RoomMember.objects.filter(user=request.user).values_list('room_id', flat=True)

    # Popular topics
    topics = Room.objects.filter(is_public=True).exclude(topic='').values_list('topic', flat=True).distinct()[:10]

    return render(request, 'rooms/list.html', {
        'rooms': rooms_qs,
        'my_room_ids': set(my_room_ids),
        'topics': topics,
        'selected_topic': topic,
        'query': query,
    })


@login_required
def room_create_view(request):
    """
    Handles creating a new community room.
    """
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES)
        if form.is_valid():
            room = RoomService.create_room(
                creator=request.user,
                name=form.cleaned_data['name'],
                topic=form.cleaned_data.get('topic', ''),
                description=form.cleaned_data.get('description', ''),
                avatar=form.cleaned_data.get('avatar'),
                is_public=form.cleaned_data.get('is_public', True)
            )
            messages.success(request, _('Room "%(name)s" created successfully.') % {'name': room.name})
            return redirect('rooms:detail', room_id=room.id)
    else:
        form = RoomForm()

    return render(request, 'rooms/create.html', {'form': form})


@login_required
def room_detail_view(request, room_id):
    """
    Renders the live room chat interface.
    """
    room = get_object_or_404(Room.objects.select_related('creator'), id=room_id)
    
    # Auto-join user if public and not already a member
    is_member = RoomMember.objects.filter(room=room, user=request.user).exists()
    if not is_member and room.is_public:
        RoomService.join_room(request.user, room)
        is_member = True
    elif not is_member and not room.is_public:
        messages.error(request, _('This is a private room.'))
        return redirect('rooms:list')

    # Load initial messages
    messages_list = RoomService.get_room_messages(room_id=room.id, limit=40)
    members = room.members.select_related('user', 'user__profile')[:20]

    return render(request, 'rooms/detail.html', {
        'room': room,
        'initial_messages': messages_list,
        'members': members,
        'is_member': is_member,
    })


@login_required
def room_join_view(request, room_id):
    """Joins a room."""
    room = get_object_or_404(Room, id=room_id)
    try:
        RoomService.join_room(request.user, room)
        messages.success(request, _('Joined "%(name)s".') % {'name': room.name})
    except Exception as e:
        messages.error(request, str(e))
    return redirect('rooms:detail', room_id=room.id)


@login_required
def room_leave_view(request, room_id):
    """Leaves a room."""
    room = get_object_or_404(Room, id=room_id)
    RoomService.leave_room(request.user, room)
    messages.info(request, _('You left the room.'))
    return redirect('rooms:list')
