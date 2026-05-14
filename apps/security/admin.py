from django.contrib import admin

from .models import ScanReport


@admin.register(ScanReport)
class ScanReportAdmin(admin.ModelAdmin):
    list_display = ('upload', 'status', 'created_at')
    list_filter = ('status',)
