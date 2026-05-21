from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html

from .models import PLAN_LABELS, PLAN_LIMITS, CouponCode, Subscription, _generate_coupon_code


def _make_set_plan_action(plan_slug, years=1):
    label = PLAN_LABELS.get(plan_slug, plan_slug)

    def action(modeladmin, request, queryset):
        expiry = timezone.now() + timezone.timedelta(days=365 * years)
        updated = queryset.update(
            plan_slug=plan_slug,
            status=Subscription.Status.ACTIVE,
            current_period_end=expiry,
        )
        messages.success(
            request,
            f'Set {updated} subscription(s) to {label} (expires {expiry.strftime("%d %b %Y")}).',
        )

    action.short_description = f'Set plan → {label}'
    action.__name__ = f'set_plan_{plan_slug}'
    return action


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user_email', 'plan_badge', 'status', 'max_projects_display',
        'current_period_end', 'updated_at',
    )
    list_filter = ('plan_slug', 'status')
    search_fields = ('user__email', 'external_customer_id')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 50

    fields = (
        'user', 'plan_slug', 'status', 'current_period_end', 'trial_ends_at',
        'external_customer_id', 'notes', 'created_at', 'updated_at',
    )

    actions = [
        _make_set_plan_action('launch_lite'),
        _make_set_plan_action('starter_cloud'),
        _make_set_plan_action('wordpress_pro'),
        _make_set_plan_action('business_cloud'),
        _make_set_plan_action('agency_turbo'),
        _make_set_plan_action('performance_max'),
        _make_set_plan_action('free'),
        'generate_coupon_action',
    ]

    def generate_coupon_action(self, request, queryset):
        """Generate coupon code(s) for selected users with a plan of your choice."""
        if 'apply' in request.POST:
            plan = request.POST.get('plan', 'launch_lite')
            valid_days = max(1, min(3650, int(request.POST.get('valid_days', 365) or 365)))
            count_per_user = max(1, min(10, int(request.POST.get('count_per_user', 1) or 1)))
            plan_label = PLAN_LABELS.get(plan, plan)

            all_codes = []
            for sub in queryset.select_related('user'):
                for _ in range(count_per_user):
                    code = _generate_coupon_code()
                    CouponCode.objects.create(
                        code=code,
                        plan=plan,
                        valid_days=valid_days,
                        created_by=request.user,
                    )
                    all_codes.append(f'{sub.user.email} → {code}')

            self.message_user(
                request,
                f'Generated {len(all_codes)} × {plan_label} code(s): {" | ".join(all_codes)}',
                messages.SUCCESS,
            )
            return None

        plan_choices = [(s, l) for s, l in Subscription.Plan.choices if s != 'free']
        return TemplateResponse(request, 'admin/billing/generate_coupon.html', {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Generate Coupon Codes',
            'subscriptions': queryset.select_related('user'),
            'selected_count': queryset.count(),
            'plan_choices': plan_choices,
        })

    generate_coupon_action.short_description = 'Generate coupon code(s) for selected users'

    @admin.display(description='Email', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description='Plan')
    def plan_badge(self, obj):
        colours = {
            'free':            '#64748b',
            'launch_lite':     '#0369a1',
            'starter_cloud':   '#0ea5e9',
            'wordpress_pro':   '#3b82f6',
            'business_cloud':  '#10b981',
            'agency_turbo':    '#8b5cf6',
            'performance_max': '#d97706',
        }
        colour = colours.get(obj.plan_slug, '#64748b')
        limit = PLAN_LIMITS.get(obj.plan_slug, 1)
        label = PLAN_LABELS.get(obj.plan_slug, obj.plan_slug)
        sites = 'Unlimited' if limit >= 999 else f'{limit} site{"s" if limit != 1 else ""}'
        expired = ''
        if obj.current_period_end and obj.current_period_end < timezone.now():
            expired = ' ⚠ expired'
            colour = '#ef4444'
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:99px;font-size:12px;font-weight:600;">'
            '{} ({}){}</span>',
            colour,
            label,
            sites,
            expired,
        )

    @admin.display(description='Max sites')
    def max_projects_display(self, obj):
        return 'Unlimited' if obj.max_projects >= 999 else obj.max_projects


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
    change_list_template = 'admin/billing/couponcode/change_list.html'

    actions = [
        _make_generate_action('launch_lite',     1),
        _make_generate_action('launch_lite',     5),
        _make_generate_action('starter_cloud',   1),
        _make_generate_action('starter_cloud',   5),
        _make_generate_action('wordpress_pro',   1),
        _make_generate_action('wordpress_pro',   5),
        _make_generate_action('business_cloud',  1),
        _make_generate_action('business_cloud',  5),
        _make_generate_action('agency_turbo',    1),
        _make_generate_action('agency_turbo',    5),
        _make_generate_action('performance_max', 1),
        _make_generate_action('performance_max', 5),
    ]

    def get_urls(self):
        from django.urls import path
        return [
            path(
                'generate-for-user/',
                self.admin_site.admin_view(self.generate_for_user_view),
                name='billing_coupon_generate_for_user',
            ),
        ] + super().get_urls()

    def generate_for_user_view(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        plan_choices = [(s, l) for s, l in Subscription.Plan.choices if s != 'free']
        error = None

        if request.method == 'POST':
            user_input = request.POST.get('user', '').strip()
            plan = request.POST.get('plan', 'launch_lite')
            valid_days = max(1, min(3650, int(request.POST.get('valid_days', 365) or 365)))
            count = max(1, min(20, int(request.POST.get('count', 1) or 1)))

            user = None
            if user_input.isdigit():
                user = User.objects.filter(pk=int(user_input)).first()
            if user is None:
                user = User.objects.filter(email__iexact=user_input).first()

            if user is None:
                error = f'No user found for "{user_input}". Try exact email or numeric ID.'
            else:
                codes = []
                for _ in range(count):
                    code = _generate_coupon_code()
                    CouponCode.objects.create(
                        code=code,
                        plan=plan,
                        valid_days=valid_days,
                        created_by=request.user,
                    )
                    codes.append(code)

                plan_label = PLAN_LABELS.get(plan, plan)
                self.message_user(
                    request,
                    f'Generated {count} × {plan_label} code(s) for {user.email}: {" | ".join(codes)}',
                    messages.SUCCESS,
                )
                return redirect('../')

        return TemplateResponse(request, 'admin/billing/generate_for_user.html', {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Generate Coupon Code for User',
            'plan_choices': plan_choices,
            'error': error,
            'post': request.POST if request.method == 'POST' else {},
        })

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
            if not obj.code:
                obj.code = _generate_coupon_code()
        super().save_model(request, obj, form, change)

    @admin.display(boolean=True, description='Redeemable')
    def is_redeemable(self, obj):
        return obj.is_redeemable
