from django.contrib import admin

from .models import QuotaUsage


@admin.register(QuotaUsage)
class QuotaUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'sampled_at', 'ram_mb_used', 'cpu_percent', 'projects_running', 'note')
    list_filter = ('sampled_at',)
