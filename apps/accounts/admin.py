from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Profile, UserPreference, OTPVerification

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

class UserPreferenceInline(admin.StackedInline):
    model = UserPreference
    can_delete = False
    verbose_name_plural = 'Preferences'

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline, UserPreferenceInline)
    list_display = ('username', 'email', 'is_verified', 'is_staff', 'last_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_verified')
    search_fields = ('username', 'email', 'phone_number')
    ordering = ('-date_joined',)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'gender', 'location_name', 'is_online', 'last_seen')
    search_fields = ('user__username', 'display_name', 'location_name')
    list_filter = ('is_online', 'gender', 'show_online_status', 'allow_random_chat')

@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'language', 'sound_enabled', 'notifications_enabled', 'dark_mode')
    list_filter = ('language', 'notifications_enabled', 'dark_mode')

@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'purpose', 'is_used', 'attempts', 'expires_at', 'created_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('identifier',)
