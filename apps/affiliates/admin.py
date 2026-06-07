from django.contrib import admin, messages

from .models import Affiliate, AffiliateApplication, AffiliateCommission
from .services import activate_affiliate_from_application


@admin.register(AffiliateApplication)
class AffiliateApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'user', 'platform', 'audience_size', 'status', 'created_at')
    list_filter = ('status', 'platform')
    list_editable = ('status',)
    list_display_links = ('name', 'email')
    search_fields = ('name', 'email', 'website', 'message', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        ('Applicant', {
            'fields': ('user', 'name', 'email', 'website', 'platform', 'audience_size'),
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

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = AffiliateApplication.objects.filter(pk=obj.pk).values_list('status', flat=True).first()
        super().save_model(request, obj, form, change)
        if obj.status == AffiliateApplication.Status.APPROVED and previous_status != AffiliateApplication.Status.APPROVED:
            affiliate = activate_affiliate_from_application(obj)
            if affiliate:
                self.message_user(
                    request,
                    f'Affiliate activated — referral code: {affiliate.code}',
                    messages.SUCCESS,
                )
            elif not obj.user_id:
                self.message_user(
                    request,
                    'Approved, but no user linked. Link a user account to generate referral links.',
                    messages.WARNING,
                )


@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('code', 'user', 'is_active', 'created_at', 'earnings_display')
    list_filter = ('is_active',)
    search_fields = ('code', 'user__email')
    readonly_fields = ('created_at',)

    @admin.display(description='Earnings')
    def earnings_display(self, obj):
        return f'₹{obj.total_earnings}'


@admin.register(AffiliateCommission)
class AffiliateCommissionAdmin(admin.ModelAdmin):
    list_display = ('affiliate', 'item_type', 'item_name', 'commission_amount', 'order', 'created_at')
    list_filter = ('item_type',)
    search_fields = ('affiliate__code', 'item_name', 'order__razorpay_order_id')
    readonly_fields = ('created_at',)
