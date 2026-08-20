from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, UserPreference

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    is_currently_online = serializers.ReadOnlyField()

    class Meta:
        model = Profile
        fields = [
            'id', 'display_name', 'avatar_url', 'bio', 'gender',
            'location_name', 'is_online', 'is_currently_online',
            'show_online_status', 'allow_random_chat', 'last_seen'
        ]

    def get_avatar_url(self, obj):
        return obj.get_avatar_url()


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_api_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_verified', 'last_active', 'profile']
