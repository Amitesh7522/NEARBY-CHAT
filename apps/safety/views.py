"""
Safety views for blocking/unblocking, report filing, and viewing blocked users list.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from .models import Block, Report
from .services import SafetyService
from apps.rooms.models import Room
from apps.chat.models import Message

User = get_user_model()

@login_required
@require_POST
def block_user_view(request, username):
    """Blocks a user and redirects back."""
    target_user = get_object_or_404(User, username=username)
    try:
        SafetyService.block_user(request.user, target_user)
        target_name = target_user.profile.get_display_name()
        messages.success(request, _('%(name)s has been blocked.') % {'name': target_name})
    except Exception as e:
        messages.error(request, str(e))

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'core:home'
    return redirect(next_url)


@login_required
@require_POST
def unblock_user_view(request, username):
    """Unblocks a user."""
    target_user = get_object_or_404(User, username=username)
    SafetyService.unblock_user(request.user, target_user)
    target_name = target_user.profile.get_display_name()
    messages.success(request, _('%(name)s has been unblocked.') % {'name': target_name})
    
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'safety:blocked_users'
    return redirect(next_url)


@login_required
def blocked_users_list_view(request):
    """Renders user's blocked users list with unblock actions."""
    blocked_list = Block.objects.filter(blocker=request.user).select_related('blocked', 'blocked__profile')
    return render(request, 'settings/blocked_users.html', {
        'blocked_list': blocked_list
    })


@login_required
def file_report_view(request):
    """Handles submission of user, room, or message safety reports."""
    if request.method == 'POST':
        reason = request.POST.get('reason', 'other')
        details = request.POST.get('details', '').strip()
        reported_username = request.POST.get('reported_username')
        reported_room_id = request.POST.get('reported_room_id')
        reported_message_id = request.POST.get('reported_message_id')

        reported_user = User.objects.filter(username=reported_username).first() if reported_username else None
        reported_room = Room.objects.filter(id=reported_room_id).first() if reported_room_id else None
        reported_message = Message.objects.filter(id=reported_message_id).first() if reported_message_id else None

        try:
            SafetyService.file_report(
                reporter=request.user,
                reason=reason,
                details=details,
                reported_user=reported_user,
                reported_room=reported_room,
                reported_message=reported_message,
            )
            messages.success(request, _('Thank you. Your report has been submitted to our moderation team.'))
        except Exception as e:
            messages.error(request, str(e))

        next_url = request.POST.get('next') or 'core:home'
        return redirect(next_url)

    # Render report modal/page
    return render(request, 'includes/modal_dialog.html')
