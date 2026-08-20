from django.contrib import admin
from .models import Room, RoomMember, RoomMessage

class RoomMemberInline(admin.TabularInline):
    model = RoomMember
    extra = 0

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'topic', 'creator', 'is_public', 'created_at')
    list_filter = ('is_public', 'topic', 'created_at')
    search_fields = ('name', 'topic', 'description', 'creator__username')
    inlines = [RoomMemberInline]

@admin.register(RoomMessage)
class RoomMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'content', 'created_at', 'is_deleted')
    list_filter = ('room', 'created_at', 'is_deleted')
    search_fields = ('content', 'sender__username')
