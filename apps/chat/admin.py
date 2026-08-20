from django.contrib import admin
from .models import Conversation, ConversationParticipant, Message, MessageStatus

class ParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ('sender', 'content', 'created_at', 'is_deleted')
    readonly_fields = ('created_at',)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'is_active', 'created_at', 'updated_at')
    list_filter = ('type', 'is_active', 'created_at')
    inlines = [ParticipantInline, MessageInline]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'message_type', 'created_at', 'is_deleted')
    list_filter = ('message_type', 'is_deleted', 'created_at')
    search_fields = ('content', 'sender__username', 'client_msg_id')
    ordering = ('-created_at',)

@admin.register(MessageStatus)
class MessageStatusAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'status', 'updated_at')
    list_filter = ('status', 'updated_at')
