"""
User, Profile, and Preference Models for Nearby Chat.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class User(AbstractUser):
    """
    Custom User Model for Nearby Chat.
    Uses UUID primary key and unique email.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    phone_number = models.CharField(_('phone number'), max_length=20, blank=True, null=True, unique=True)
    is_verified = models.BooleanField(_('verified account'), default=False)
    last_active = models.DateTimeField(_('last active timestamp'), default=timezone.now)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['last_active']),
        ]

    def __str__(self):
        return self.username


class Interest(models.Model):
    """
    User interest/passion tag for discovery, matching, and shared profile badges.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_('Name'), max_length=50, unique=True)
    slug = models.SlugField(_('Slug'), max_length=50, unique=True)
    emoji = models.CharField(_('Emoji Icon'), max_length=10, blank=True, default='✨')
    category = models.CharField(_('Category'), max_length=50, blank=True, default='General')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Interest')
        verbose_name_plural = _('Interests')
        ordering = ['name']

    def __str__(self):
        return f"{self.emoji} {self.name}"


import secrets
import string

COMMUNITY_BADGES = {
    'new_member': {
        'id': 'new_member',
        'name': _('New Member'),
        'emoji': '🌱',
        'description': _('Awarded to newer members of the Nearby Chat community.'),
        'css_class': 'badge-new-member',
    },
    'active_member': {
        'id': 'active_member',
        'name': _('Active Member'),
        'emoji': '✨',
        'description': _('Reflects regular participation and activity on Nearby Chat.'),
        'css_class': 'badge-active-member',
    },
    'connector': {
        'id': 'connector',
        'name': _('Connector'),
        'emoji': '🤝',
        'description': _('Reflects successful contribution to growing the Nearby Chat community.'),
        'css_class': 'badge-connector',
    },
    'trusted_member': {
        'id': 'trusted_member',
        'name': _('Trusted Member'),
        'emoji': '⭐',
        'description': _('Reflects sustained positive participation and trust in the community.'),
        'css_class': 'badge-trusted-member',
    },
}

PRESET_AVATARS = ['astro', 'robot', 'fox', 'panda', 'cat', 'bear', 'lion', 'alien']

def generate_invite_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

def generate_unique_user_identity():
    """
    Generates a unique random 4-5 digit number for new users.
    Returns (username, display_name, deterministic_preset). E.g. ('user_4821', 'User 4821', 'fox')
    """
    import random
    while True:
        num = random.randint(1000, 99999)
        uname = f"user_{num}"
        if not User.objects.filter(username=uname).exists():
            preset = PRESET_AVATARS[num % len(PRESET_AVATARS)]
            return uname, f"User {num}", preset


class Profile(models.Model):
    """
    Public and social profile details for a user.
    """
    GENDER_CHOICES = [
        ('prefer_not_to_say', _('Prefer not to say')),
        ('male', _('Male')),
        ('female', _('Female')),
        ('non_binary', _('Non-binary')),
        ('other', _('Other')),
    ]

    BADGE_CHOICES = [
        ('new_member', _('New Member')),
        ('active_member', _('Active Member')),
        ('connector', _('Connector')),
        ('trusted_member', _('Trusted Member')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(_('Display Name'), max_length=60, blank=True)
    is_temporary_name = models.BooleanField(_('Temporary Display Name'), default=True, help_text=_('True if using auto-generated User {number}'))
    avatar = models.ImageField(_('Avatar'), upload_to='avatars/%Y/%m/', blank=True, null=True)
    avatar_preset = models.CharField(_('Cartoon Avatar Preset'), max_length=50, blank=True, default='')
    bio = models.TextField(_('Bio'), max_length=500, blank=True)
    gender = models.CharField(_('Gender'), max_length=20, choices=GENDER_CHOICES, default='prefer_not_to_say')
    date_of_birth = models.DateField(_('Date of Birth'), blank=True, null=True)
    
    # Location (Optional discovery attributes)
    location_name = models.CharField(_('Location / City'), max_length=120, blank=True)
    latitude = models.DecimalField(_('Latitude'), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_('Longitude'), max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Interests & Passions
    interests = models.ManyToManyField(Interest, related_name='profiles', blank=True)
    
    # Community & Referrals
    invite_code = models.CharField(_('Invite Code'), max_length=12, db_index=True, blank=True, default='')
    badge = models.CharField(_('Community Badge'), max_length=20, choices=BADGE_CHOICES, default='new_member', db_index=True)

    # Online Presence & Discovery Preferences
    is_online = models.BooleanField(_('Online Status'), default=False, db_index=True)
    last_seen = models.DateTimeField(_('Last Seen'), default=timezone.now)
    show_online_status = models.BooleanField(_('Show Online Status to others'), default=True)
    allow_random_chat = models.BooleanField(_('Allow Random Chat Discovery'), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Profile')
        verbose_name_plural = _('Profiles')
        indexes = [
            models.Index(fields=['is_online', 'show_online_status']),
            models.Index(fields=['allow_random_chat']),
            models.Index(fields=['invite_code']),
            models.Index(fields=['badge']),
        ]

    def __str__(self):
        return self.get_display_name()

    def save(self, *args, **kwargs):
        if not self.invite_code:
            code = generate_invite_code()
            while Profile.objects.filter(invite_code=code).exists():
                code = generate_invite_code()
            self.invite_code = code
        super().save(*args, **kwargs)

    def get_display_name(self):
        return self.display_name or self.user.username

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        if self.avatar_preset:
            return f'/static/images/avatars/{self.avatar_preset}.svg'
        return '/static/images/default-avatar.svg'

    def get_badge_details(self):
        return COMMUNITY_BADGES.get(self.badge, COMMUNITY_BADGES['new_member'])

    @property
    def is_profile_completed(self):
        """Returns True if the user has customized their display name and added at least 1 interest."""
        has_real_name = not self.is_temporary_name and bool(self.display_name)
        has_interests = self.interests.exists()
        return has_real_name and has_interests

    def get_completion_checklist(self):
        """Returns a checklist dict for profile completion UI."""
        has_name = not self.is_temporary_name and bool(self.display_name)
        has_photo = bool(self.avatar) or bool(self.avatar_preset)
        has_gender = self.gender not in ('', 'prefer_not_to_say', None)
        has_interests = self.interests.exists()
        
        total_items = 4
        completed_items = sum([1 for item in [has_name, has_photo, has_gender, has_interests] if item])
        percentage = int((completed_items / total_items) * 100)
        
        return {
            'has_name': has_name,
            'has_photo': has_photo,
            'has_gender': has_gender,
            'has_interests': has_interests,
            'completed_count': completed_items,
            'total_count': total_items,
            'percentage': percentage,
            'is_completed': completed_items >= 3,
        }

    @property
    def is_currently_online(self):
        if not self.show_online_status:
            return False
        # If user active in last 3 minutes or explicitly online
        if self.is_online:
            return True
        return (timezone.now() - self.last_seen).total_seconds() < 180


class Referral(models.Model):
    """
    Tracks community invitations and their qualification status persistently.
    Strictly prevents duplicate claims and self-referrals.
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('qualified', _('Qualified')),
        ('invalidated', _('Invalidated')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_referrals')
    referred_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='received_referral')
    invite_code = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending', db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    qualified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Referral')
        verbose_name_plural = _('Referrals')
        indexes = [
            models.Index(fields=['inviter', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.inviter.username} -> {self.referred_user.username} ({self.status})"



class UserPreference(models.Model):
    """
    User settings and preferences (Language, notifications, audio).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    language = models.CharField(_('Language'), max_length=10, choices=[('en', 'English'), ('hi', 'Hindi')], default='en')
    sound_enabled = models.BooleanField(_('Chat Sound Effects'), default=True)
    notifications_enabled = models.BooleanField(_('In-app Notifications'), default=True)
    email_notifications = models.BooleanField(_('Email Notifications'), default=False)
    dark_mode = models.BooleanField(_('Dark Mode'), default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('User Preference')
        verbose_name_plural = _('User Preferences')

    def __str__(self):
        return f"{self.user.username} Preferences ({self.language})"


class OTPVerification(models.Model):
    """
    Verification model for SMS / Email OTP verification codes.
    """
    PURPOSE_CHOICES = [
        ('signup', _('Signup')),
        ('login', _('Login')),
        ('password_reset', _('Password Reset')),
        ('phone_verify', _('Phone Verification')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identifier = models.CharField(_('Email or Phone'), max_length=100, db_index=True)
    otp_hash = models.CharField(_('Hashed OTP'), max_length=128)
    purpose = models.CharField(_('Purpose'), max_length=20, choices=PURPOSE_CHOICES, default='signup')
    expires_at = models.DateTimeField(_('Expires At'))
    is_used = models.BooleanField(_('Is Used'), default=False)
    attempts = models.PositiveSmallIntegerField(_('Attempts'), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('OTP Verification')
        verbose_name_plural = _('OTP Verifications')
        indexes = [
            models.Index(fields=['identifier', 'purpose', 'is_used']),
        ]

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at and self.attempts < 5
