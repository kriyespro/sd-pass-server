from django.contrib import admin

from .models import PlatformTlsConfig


@admin.register(PlatformTlsConfig)
class PlatformTlsConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'cert_resolver_name', 'acme_contact_email')
