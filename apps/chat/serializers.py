from rest_framework import serializers
from .models import Message, Conversation, ConversationParticipant

class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.CharField(source='sender.id', read_only=True)
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_name = serializers.SerializerMethodField()
    sender_avatar = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'client_msg_id', 'sender_id', 'sender_username',
            'sender_name', 'sender_avatar', 'content', 'message_type',
            'image', 'created_at', 'is_deleted'
        ]

    def get_sender_name(self, obj):
        if not obj.sender:
            return 'System'
        return obj.sender.profile.get_display_name() if hasattr(obj.sender, 'profile') else obj.sender.username

    def get_sender_avatar(self, obj):
        if not obj.sender:
            return '/static/images/default-avatar.svg'
        return obj.sender.profile.get_avatar_url() if hasattr(obj.sender, 'profile') else '/static/images/default-avatar.svg'
