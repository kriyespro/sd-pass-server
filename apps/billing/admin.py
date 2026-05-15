from django.contrib import admin, messages

from .models import PLAN_LABELS, CouponCode, Subscription, _generate_coupon_code


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan_slug', 'status', 'max_projects_display', 'current_period_end', 'updated_at')
    list_filter = ('plan_slug', 'status')
    search_fields = ('user__email', 'external_customer_id')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Max projects')
    def max_projects_display(self, obj):
        return obj.max_projects


def _make_generate_action(plan_slug, count):
    def action(modeladmin, request, queryset):
        created = []
        for _ in range(count):
            code = _generate_coupon_code()
            CouponCode.objects.create(
                code=code,
                plan=plan_slug,
                created_by=request.user,
            )
            created.append(code)
        messages.success(
            request,
            f'Generated {count} {plan_slug.upper()} coupon(s): {", ".join(created)}',
        )
    action.short_description = f'Generate {count} {PLAN_LABELS.get(plan_slug, plan_slug)} coupon(s)'
    action.__name__ = f'generate_{count}_{plan_slug}'
    return action


@admin.register(CouponCode)
class CouponCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'plan', 'is_active', 'is_redeemable', 'used_by', 'redeemed_at', 'expires_at', 'created_at')
    list_filter = ('plan', 'is_active')
    search_fields = ('code', 'used_by__email')
    raw_id_fields = ('used_by', 'created_by')
    readonly_fields = ('redeemed_at', 'created_at', 'created_by')
    ordering = ('-created_at',)

    actions = [
        _make_generate_action('starter',  1),
        _make_generate_action('starter',  5),
        _make_generate_action('starter',  10),
        _make_generate_action('pro',      1),
        _make_generate_action('pro',      5),
        _make_generate_action('pro',      10),
        _make_generate_action('business', 1),
        _make_generate_action('business', 5),
        _make_generate_action('business', 10),
    ]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            if not obj.code:
                obj.code = _generate_coupon_code()
        super().save_model(request, obj, form, change)

    @admin.display(boolean=True, description='Redeemable')
    def is_redeemable(self, obj):
        return obj.is_redeemable
