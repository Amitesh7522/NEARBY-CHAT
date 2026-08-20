"""
Core views: Home Discovery, Settings Hub, Privacy Controls, Localization, and Legal Documents.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.translation import gettext_lazy as _, activate
from django.utils import timezone
from django.conf import settings
from datetime import datetime

from apps.accounts.models import Profile, UserPreference, Interest
from apps.accounts.forms import UserPreferenceForm
from apps.rooms.models import Room, RoomMember
from apps.chat.services import ChatService
from apps.safety.models import Block

User = get_user_model()

import math

def calculate_distance_km(lat1, lon1, lat2, lon2):
    """
    Calculates great-circle distance between two coordinates in kilometers.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(6371 * c, 1)
    except (ValueError, TypeError):
        return None

@login_required
def home_view(request):
    """
    Main Discovery & Social Dashboard with Interest & Location Proximity Filtering.
    """
    now_hour = timezone.localtime().hour
    if now_hour < 12:
        greeting = _("Good morning")
    elif now_hour < 17:
        greeting = _("Good afternoon")
    else:
        greeting = _("Good evening")

    # Exclude self and blocked users from discovery
    blocked_by_user = Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
    blocking_user = Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
    exclude_ids = set(list(blocked_by_user) + list(blocking_user) + [request.user.id])

    my_profile = request.user.profile
    my_lat = my_profile.latitude
    my_lon = my_profile.longitude
    selected_radius = request.GET.get('radius', '').strip() # '5', '15', '50', 'city', ''
    selected_interest = request.GET.get('interest', '').strip()

    # Available / Online Users
    online_users_qs = User.objects.filter(
        profile__is_online=True,
        profile__show_online_status=True
    ).exclude(id__in=exclude_ids).select_related('profile').prefetch_related('profile__interests')[:10]

    online_users = list(online_users_qs)
    for u in online_users:
        dist = calculate_distance_km(my_lat, my_lon, u.profile.latitude, u.profile.longitude)
        u.distance_km = dist
        if dist is not None:
            u.distance_display = f"~{dist} km"
        elif u.profile.location_name:
            u.distance_display = u.profile.location_name
        else:
            u.distance_display = ""

    # Current user's interests
    my_interest_ids = set(my_profile.interests.values_list('id', flat=True))

    # Discover People (nearby / suggested with optional interest & radius filter)
    discover_qs = User.objects.filter(
        profile__allow_random_chat=True
    ).exclude(id__in=exclude_ids).select_related('profile').prefetch_related('profile__interests')

    if selected_interest:
        discover_qs = discover_qs.filter(profile__interests__slug=selected_interest)

    discover_users_list = list(discover_qs.distinct()[:30])

    # Annotate shared interests & distances
    for u in discover_users_list:
        user_interests = list(u.profile.interests.all())
        u.shared_interests = [i for i in user_interests if i.id in my_interest_ids]
        u.shared_count = len(u.shared_interests)
        dist = calculate_distance_km(my_lat, my_lon, u.profile.latitude, u.profile.longitude)
        u.distance_km = dist
        if dist is not None:
            u.distance_display = f"~{dist} km"
        elif u.profile.location_name:
            u.distance_display = u.profile.location_name
        else:
            u.distance_display = ""

    # Radius filtering
    if selected_radius == '5':
        discover_users_list = [u for u in discover_users_list if u.distance_km is not None and u.distance_km <= 5.0]
    elif selected_radius == '15':
        discover_users_list = [u for u in discover_users_list if u.distance_km is not None and u.distance_km <= 15.0]
    elif selected_radius == '50':
        discover_users_list = [u for u in discover_users_list if u.distance_km is not None and u.distance_km <= 50.0]
    elif selected_radius == 'city' and my_profile.location_name:
        discover_users_list = [u for u in discover_users_list if u.profile.location_name and u.profile.location_name.strip().lower() == my_profile.location_name.strip().lower()]

    # Sort prioritized by: distance (if available), then shared interests, then online status
    discover_users_list.sort(key=lambda u: (
        u.distance_km if u.distance_km is not None else 9999,
        -u.shared_count,
        0 if u.profile.is_currently_online else 1,
    ))

    # Featured Rooms
    featured_rooms = Room.objects.filter(is_public=True).select_related('creator').order_by('-updated_at')[:6]

    # Recent Conversations (up to 3 for quick jump)
    recent_chats = ChatService.get_user_conversations_summary(request.user)[:3]

    all_interests = Interest.objects.all()

    return render(request, 'home/index.html', {
        'greeting': greeting,
        'online_users': online_users,
        'discover_users': discover_users_list[:12],
        'featured_rooms': featured_rooms,
        'recent_chats': recent_chats,
        'all_interests': all_interests,
        'selected_interest': selected_interest,
        'selected_radius': selected_radius,
        'user_has_location': bool(my_lat and my_lon),
        'user_location_name': my_profile.location_name,
    })


@login_required
def settings_view(request):
    """
    Settings overview hub accessed from top-left hamburger menu.
    """
    return render(request, 'settings/index.html')


@login_required
def privacy_settings_view(request):
    """
    Manage online status visibility and random chat discovery toggles.
    """
    profile = request.user.profile

    if request.method == 'POST':
        profile.show_online_status = request.POST.get('show_online_status') == 'on'
        profile.allow_random_chat = request.POST.get('allow_random_chat') == 'on'
        profile.save(update_fields=['show_online_status', 'allow_random_chat'])
        messages.success(request, _('Privacy settings updated.'))
        return redirect('core:privacy_settings')

    return render(request, 'settings/privacy.html', {'profile': profile})


@login_required
def notification_settings_view(request):
    """
    Manage sound effects and notification preferences.
    """
    pref, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        pref.sound_enabled = request.POST.get('sound_enabled') == 'on'
        pref.notifications_enabled = request.POST.get('notifications_enabled') == 'on'
        pref.email_notifications = request.POST.get('email_notifications') == 'on'
        pref.save(update_fields=['sound_enabled', 'notifications_enabled', 'email_notifications'])
        messages.success(request, _('Notification preferences saved.'))
        return redirect('core:notification_settings')

    return render(request, 'settings/notifications.html', {'pref': pref})


@login_required
def language_settings_view(request):
    """
    Switch application language between English and Hindi.
    """
    pref, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        selected_lang = request.POST.get('language', 'en')
        if selected_lang in ['en', 'hi']:
            pref.language = selected_lang
            pref.save(update_fields=['language'])
            request.session['django_language'] = selected_lang
            activate(selected_lang)
            messages.success(request, _('Language updated successfully.'))
            return redirect('core:language_settings')

    return render(request, 'settings/language.html', {
        'current_language': pref.language,
        'languages': settings.LANGUAGES,
    })


def privacy_policy_view(request):
    """
    Production-ready structured Privacy Policy.
    """
    return render(request, 'legal/privacy_policy.html')


def terms_of_use_view(request):
    """
    Production-ready structured Terms of Use.
    """
    return render(request, 'legal/terms_of_use.html')


def help_support_view(request):
    """
    Help & Support FAQ and assistance page.
    """
    if request.method == 'POST':
        messages.success(request, _('Thank you for contacting support. We will get back to you shortly.'))
        return redirect('core:help_support')
    return render(request, 'legal/help_support.html')


@login_required
def invite_friends_view(request):
    """
    Dedicated Invite Friends screen displaying user's unique invite link,
    social share actions, and community progress toward badges.
    """
    from apps.accounts.services import ReferralService, BadgeService
    from apps.accounts.models import COMMUNITY_BADGES

    invite_code = request.user.profile.invite_code
    if not invite_code:
        request.user.profile.save()
        invite_code = request.user.profile.invite_code

    invite_url = request.build_absolute_uri(f'/invite/{invite_code}/')
    invite_progress = ReferralService.get_inviter_progress(request.user)
    badge_details = request.user.profile.get_badge_details()

    return render(request, 'core/invite.html', {
        'invite_code': invite_code,
        'invite_url': invite_url,
        'invite_progress': invite_progress,
        'badge_details': badge_details,
        'all_badges': COMMUNITY_BADGES.values(),
    })


def invite_landing_view(request, code):
    """
    Handles when an invite link (/invite/<code>/) is opened by a new user.
    Saves invite code in session and redirects to registration.
    """
    clean_code = str(code).strip().upper()
    
    if request.user.is_authenticated:
        messages.info(request, _('You are already registered on Nearby Chat!'))
        return redirect('core:home')

    # Store in session for registration attribution
    request.session['invite_code'] = clean_code
    return redirect(f'/accounts/register/?ref={clean_code}')

