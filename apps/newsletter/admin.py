from django.contrib import admin, messages
from django.utils.html import format_html

from .models import NewsletterSync


def _status_badge(status):
    colors = {
        'pending': '#6c757d',
        'running': '#0d6efd',
        'done': '#198754',
        'failed': '#dc3545',
    }
    color = colors.get(status, '#6c757d')
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{}</span>',
        color, status.upper()
    )


@admin.register(NewsletterSync)
class NewsletterSyncAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status_badge', 'total', 'synced', 'failed',
        'duration', 'triggered_by', 'created_at',
    )
    list_filter = ('status',)
    readonly_fields = (
        'status', 'total', 'synced', 'skipped', 'failed',
        'error', 'started_at', 'finished_at', 'created_at', 'triggered_by',
    )
    actions = ['trigger_full_sync']

    def status_badge(self, obj):
        return _status_badge(obj.status)
    status_badge.short_description = 'Status'
    status_badge.allow_tags = True

    def duration(self, obj):
        d = obj.duration_seconds
        return f'{d}s' if d is not None else '—'
    duration.short_description = 'Duration'

    def trigger_full_sync(self, request, queryset):
        from .models import NewsletterSync
        from .tasks import sync_all_users

        sync = NewsletterSync.objects.create(triggered_by=request.user)
        sync_all_users.delay(sync_id=sync.pk)
        self.message_user(
            request,
            f'Sync #{sync.pk} queued — syncing all active users to Systeme.io.',
            messages.SUCCESS,
        )
    trigger_full_sync.short_description = 'Sync ALL users → Systeme.io now'

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.contrib.auth import get_user_model
        User = get_user_model()
        extra_context['total_users'] = User.objects.filter(is_active=True).count()
        extra_context['last_sync'] = NewsletterSync.objects.filter(
            status=NewsletterSync.Status.DONE
        ).first()
        return super().changelist_view(request, extra_context=extra_context)
