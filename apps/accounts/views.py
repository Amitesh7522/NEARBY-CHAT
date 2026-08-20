"""
Accounts views: Authentication, Profiles, Settings, and Account Deletion.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .forms import UserRegisterForm, UserLoginForm, ProfileEditForm, UserPreferenceForm
from .models import Profile, UserPreference, Interest
from .services import VerificationService, ReferralService, BadgeService
from apps.safety.models import Block
from apps.chat.services import ChatService

User = get_user_model()

def register_view(request):
    """Handles new user registration with interest selection."""
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.save()

                display_name = form.cleaned_data.get('display_name')
                if hasattr(user, 'profile'):
                    if display_name:
                        user.profile.display_name = display_name
                    interests = form.cleaned_data.get('interests')
                    if interests:
                        user.profile.interests.set(interests)
                    user.profile.save()

            login(request, user, backend='apps.accounts.backends.EmailOrUsernameModelBackend')

            # Record community invite / referral attribution if invite code present
            invite_code = request.session.pop('invite_code', None) or request.GET.get('ref', '')
            if invite_code:
                ip = request.META.get('REMOTE_ADDR')
                ReferralService.record_referral(invite_code=invite_code, referred_user=user, ip_address=ip)

            messages.success(request, _('Welcome to Nearby Chat! Your account is ready.'))
            return redirect('core:home')
    else:
        form = UserRegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'all_interests': Interest.objects.all(),
    })


def login_view(request):
    """User login using Username or Phone Number."""
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, _('Welcome back, %(username)s!') % {'username': user.profile.get_display_name()})
            next_url = request.GET.get('next') or 'core:home'
            return redirect(next_url)
    else:
        form = UserLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """User logout."""
    logout(request)
    messages.info(request, _('You have been logged out.'))
    return redirect('accounts:login')


@login_required
def profile_view(request, username=None):
    """
    View user's own profile or a public profile of another user.
    Includes rating statistics and unrated qualifying chat detection.
    """
    is_own_profile = username is None or username == request.user.username
    can_rate = False
    unrated_conversation_id = ''

    if is_own_profile:
        target_user = request.user
        is_blocked = False
    else:
        target_user = get_object_or_404(User.objects.select_related('profile'), username=username)
        # Check if blocker or blocked
        is_blocked = Block.objects.filter(
            blocker=request.user, blocked=target_user
        ).exists() or Block.objects.filter(
            blocker=target_user, blocked=request.user
        ).exists()

        if not is_blocked and request.user.is_authenticated:
            unrated_conv = ChatService.get_unrated_qualifying_conversation(request.user, target_user)
            if unrated_conv:
                can_rate = True
                unrated_conversation_id = str(unrated_conv.id)

    profile = getattr(target_user, 'profile', None)
    if profile:
        BadgeService.evaluate_user_badge(target_user)
    
    badge_details = profile.get_badge_details() if profile else None
    invite_progress = ReferralService.get_inviter_progress(request.user) if is_own_profile else None
    rating_summary = ChatService.get_user_rating_summary(target_user)

    return render(request, 'accounts/profile.html', {
        'target_user': target_user,
        'profile': profile,
        'is_own_profile': is_own_profile,
        'is_blocked': is_blocked,
        'can_rate': can_rate,
        'unrated_conversation_id': unrated_conversation_id,
        'rating_summary': rating_summary,
        'badge_details': badge_details,
        'invite_progress': invite_progress,
    })


PRESET_AVATARS = [
    ('fox', _('Clever Fox')),
    ('panda', _('Chill Panda')),
    ('cat', _('Cyber Cat')),
    ('robot', _('Astro Bot')),
    ('astro', _('Space Explorer')),
    ('lion', _('Brave Lion')),
    ('bear', _('Cozy Bear')),
    ('alien', _('Neon Alien')),
]


@login_required
def edit_profile_view(request):
    """Edit display name, avatar, bio, location, and discovery flags."""
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            # If a new file is uploaded, clear preset
            if 'avatar' in request.FILES and request.FILES['avatar']:
                profile.avatar_preset = ''
            form.save()
            messages.success(request, _('Profile updated successfully.'))
            return redirect('accounts:profile')
    else:
        form = ProfileEditForm(instance=profile)

    return render(request, 'accounts/edit_profile.html', {
        'form': form,
        'profile': profile,
        'preset_avatars': PRESET_AVATARS,
        'all_interests': Interest.objects.all(),
    })


@login_required
def delete_account_view(request):
    """
    Genuine Account Deletion.
    Deletes user account, removes conversations, clean up memberships and uploaded files.
    """
    if request.method == 'POST':
        confirm_password = request.POST.get('password')
        if not request.user.check_password(confirm_password):
            messages.error(request, _('Incorrect password. Account deletion cancelled.'))
            return render(request, 'accounts/delete_account.html')

        user = request.user
        # Clean up files
        if hasattr(user, 'profile') and user.profile.avatar:
            try:
                user.profile.avatar.delete(save=False)
            except Exception:
                pass

        # Perform atomic deletion
        with transaction.atomic():
            logout(request)
            user.delete()

        messages.info(request, _('Your account and associated data have been permanently deleted.'))
        return redirect('accounts:login')

    return render(request, 'accounts/delete_account.html')


# ==============================================================================
# REST API Endpoints for OTP & Profile
# ==============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp_api(request):
    """Dispatches a real OTP to the given phone or email."""
    identifier = request.data.get('identifier', '').strip()
    purpose = request.data.get('purpose', 'signup')

    if not identifier:
        return Response({'error': _('Phone number or email is required.')}, status=status.HTTP_400_BAD_REQUEST)

    success, msg = VerificationService.send_otp_challenge(identifier, purpose)
    if success:
        return Response({'message': msg, 'status': 'sent'})
    return Response({'error': msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_api(request):
    """Validates the supplied OTP."""
    identifier = request.data.get('identifier', '').strip()
    otp = request.data.get('otp', '').strip()
    purpose = request.data.get('purpose', 'signup')

    if not identifier or not otp:
        return Response({'error': _('Identifier and OTP are required.')}, status=status.HTTP_400_BAD_REQUEST)

    is_valid = VerificationService.verify_otp_challenge(identifier, otp, purpose)
    if is_valid:
        return Response({'message': _('Verification successful.'), 'verified': True})
    return Response({'error': _('Invalid or expired verification code.')}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_location_api(request):
    """
    Updates the authenticated user's coordinates with privacy fuzzing.
    Protects exact home coordinates while maintaining high-accuracy proximity.
    """
    import random
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    location_name = request.data.get('location_name', '').strip()

    if latitude is None or longitude is None:
        return Response({'error': _('Latitude and longitude are required.')}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lat = float(latitude)
        lon = float(longitude)

        # Privacy preservation: apply slight fuzzing (±0.0025 deg ~ 250-300m)
        fuzz_lat = lat + random.uniform(-0.0025, 0.0025)
        fuzz_lon = lon + random.uniform(-0.0025, 0.0025)

        profile = request.user.profile
        profile.latitude = round(fuzz_lat, 6)
        profile.longitude = round(fuzz_lon, 6)
        if location_name:
            profile.location_name = location_name
        profile.save(update_fields=['latitude', 'longitude', 'location_name'])

        return Response({
            'success': True,
            'message': _('Location updated successfully.'),
            'location_name': profile.location_name,
        })
    except (ValueError, TypeError):
        return Response({'error': _('Invalid coordinates provided.')}, status=status.HTTP_400_BAD_REQUEST)

