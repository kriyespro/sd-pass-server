from django.contrib import admin

from .models import AffiliateApplication


@admin.register(AffiliateApplication)
class AffiliateApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'platform', 'audience_size', 'status', 'created_at')
    list_filter = ('status', 'platform')
    list_editable = ('status',)
    list_display_links = ('name', 'email')
    search_fields = ('name', 'email', 'website', 'message')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        ('Applicant', {
            'fields': ('name', 'email', 'website', 'platform', 'audience_size'),
        }),
        ('Application', {
            'fields': ('message',),
        }),
        ('Review', {
            'fields': ('status', 'admin_notes'),
        }),
        ('Meta', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
