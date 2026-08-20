from django.contrib import admin
from .models import MatchQueue

@admin.register(MatchQueue)
class MatchQueueAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'preferred_language', 'queued_at')
    list_filter = ('status', 'preferred_language')
