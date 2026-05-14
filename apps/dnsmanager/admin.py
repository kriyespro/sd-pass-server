from django.contrib import admin

from .models import DnsRecord


@admin.register(DnsRecord)
class DnsRecordAdmin(admin.ModelAdmin):
    list_display = ('fqdn', 'project', 'record_type', 'target_ip', 'status', 'updated_at')
    list_filter = ('status', 'record_type')
    search_fields = ('fqdn', 'project__slug')
