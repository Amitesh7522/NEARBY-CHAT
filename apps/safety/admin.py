from django.contrib import admin
from django.utils import timezone
from .models import Block, Report, ModerationAction

@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'created_at')
    search_fields = ('blocker__username', 'blocked__username')

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'reported_user', 'reported_room', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('reporter__username', 'reported_user__username', 'details', 'moderator_notes')
    readonly_fields = ('created_at',)
    actions = ['mark_as_investigating', 'mark_as_resolved', 'mark_as_dismissed']

    def mark_as_investigating(self, request, queryset):
        queryset.update(status='investigating', reviewed_at=timezone.now())
    mark_as_investigating.short_description = "Mark selected reports as Under Investigation"

    def mark_as_resolved(self, request, queryset):
        queryset.update(status='resolved', reviewed_at=timezone.now())
    mark_as_resolved.short_description = "Mark selected reports as Resolved (Action Taken)"

    def mark_as_dismissed(self, request, queryset):
        queryset.update(status='dismissed', reviewed_at=timezone.now())
    mark_as_dismissed.short_description = "Dismiss selected reports"

@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'moderator', 'is_active', 'expires_at', 'created_at')
    list_filter = ('action_type', 'is_active', 'created_at')
    search_fields = ('user__username', 'reason')
