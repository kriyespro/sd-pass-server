from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan_slug', 'status', 'current_period_end', 'updated_at')
    list_filter = ('plan_slug', 'status')
    search_fields = ('user__email', 'external_customer_id')
    raw_id_fields = ('user',)
