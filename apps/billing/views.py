import hashlib
import hmac
import json
import logging
from decimal import Decimal

import razorpay
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import FormView

logger = logging.getLogger(__name__)

from .models import PLAN_LABELS, PLAN_LIMITS, PLAN_PRICES, PlanAddon, Subscription
from .services import get_or_create_subscription, redeem_coupon


class CouponForm(forms.Form):
    code = forms.CharField(
        label='Coupon code',
        max_length=32,
        widget=forms.TextInput(attrs={
            'class': (
                'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
                'text-slate-100 font-mono uppercase tracking-widest outline-none '
                'ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
            ),
            'placeholder': 'e.g. ABCD-1234-EFGH-5678',
            'autocomplete': 'off',
            'autocorrect': 'off',
            'spellcheck': 'false',
        }),
    )


class RedeemCouponView(LoginRequiredMixin, FormView):
    template_name = 'pages/billing/redeem.jinja'
    form_class = CouponForm
    success_url = reverse_lazy('billing:redeem')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            sub = get_or_create_subscription(self.request.user)
        except Exception as exc:
            logger.exception('RedeemCouponView: get_or_create_subscription failed: %s', exc)
            raise
        ctx['subscription'] = sub
        ctx['plan_labels'] = PLAN_LABELS
        ctx['plan_limits'] = PLAN_LIMITS
        ctx['plan_prices'] = PLAN_PRICES
        ctx['razorpay_key_id'] = settings.RAZORPAY_KEY_ID
        ctx['active_addons'] = list(
            PlanAddon.objects.filter(
                user=self.request.user,
                status=PlanAddon.Status.ACTIVE,
                current_period_end__gt=timezone.now(),
            ).order_by('-created_at')
        )
        ctx['plans'] = [
            {
                'slug': 'test_plan',
                'name': 'Starter Trial',
                'subtitle': 'India · 1 Website · Custom Domain · 30 Days',
                'sites': '1',
                'price': '₹299',
                'period': '30 days',
                'specs': '1 website · Custom domain · Upgrade anytime · Suspends after 30 days',
                'highlight': False,
            },
            {
                'slug': 'launch_lite',
                'name': 'Launch Lite',
                'subtitle': 'India · 1 Website',
                'sites': '1',
                'price': '₹1,499',
                'period': 'year',
                'specs': '521 MB RAM · Shared CPU · 1 GB SSD',
                'highlight': False,
            },
            {
                'slug': 'starter_cloud',
                'name': 'Starter Cloud',
                'subtitle': 'India · 1 Website · Free SSL',
                'sites': '1',
                'price': '₹2,099',
                'period': 'year',
                'specs': '1 GB RAM · 1 vCPU · 15 GB NVMe SSD',
                'highlight': False,
            },
            {
                'slug': 'wordpress_pro',
                'name': 'WordPress Pro',
                'subtitle': 'India · 1 Website · 1 Flask App',
                'sites': '1',
                'price': '₹3,699',
                'period': 'year',
                'specs': '2 GB RAM · 2 vCPU · 30 GB SSD · Flask + SQLite',
                'flask': 1,
                'highlight': False,
            },
            {
                'slug': 'business_cloud',
                'name': 'Business Cloud',
                'subtitle': 'India · 5 Static or 1 Flask + 4 Static',
                'sites': '5',
                'price': '₹5,999',
                'period': 'year',
                'specs': '4 GB RAM · 2 vCPU · 60 GB SSD · Flask + SQLite',
                'flask': 1,
                'highlight': True,
            },
            {
                'slug': 'agency_turbo',
                'name': 'Agency Turbo',
                'subtitle': 'India · 10 Sites · 3 Flask Apps',
                'sites': '10',
                'price': '₹8,499',
                'period': 'year',
                'specs': '6 GB RAM · 4 vCPU · 80 GB NVMe SSD · HTML · CSS · Tailwind · JS · SQLite · Flask',
                'flask': 3,
                'highlight': False,
            },
            {
                'slug': 'performance_max',
                'name': 'Performance Max',
                'subtitle': 'USA · Unlimited Sites · 5 Flask Apps',
                'sites': 'Unlimited',
                'price': '₹11,999',
                'period': 'year',
                'specs': '6 GB RAM · 4 vCPU · 120 GB NVMe SSD · HTML · CSS · Tailwind · JS · SQLite · Flask',
                'flask': 5,
                'highlight': False,
            },
        ]
        ctx['flask_addon'] = {
            'slug': 'flask_addon',
            'name': 'Flask Add-on',
            'subtitle': 'Add 1 Flask app slot to any eligible plan',
            'price': '₹1,499',
            'period': 'year',
            'specs': 'Python · Flask · SQLite · Requires WordPress Pro or higher base plan',
        }
        return ctx

    def form_valid(self, form):
        ok, result = redeem_coupon(self.request.user, form.cleaned_data['code'])
        if ok:
            label = PLAN_LABELS.get(result, result)
            messages.success(
                self.request,
                f'🎉 Coupon redeemed! You are now on the {label} plan.',
            )
            # Redirect so the plan badge refreshes and browser back-button won't re-submit
            return HttpResponseRedirect(reverse('billing:redeem'))
        else:
            messages.error(self.request, result)
            return self.render_to_response(self.get_context_data(form=form))


@login_required
@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    plan_slug = data.get('plan_slug', '')
    if plan_slug not in PLAN_PRICES:
        return JsonResponse({'error': 'Invalid plan'}, status=400)

    plan_price = PLAN_PRICES[plan_slug]
    credit_to_apply = Decimal(str(data.get('credit_amount', 0) or 0)).quantize(Decimal('0.01'))

    # Validate and cap credit against partner balance
    if credit_to_apply > 0:
        from apps.affiliates.services import get_or_create_partner
        partner = get_or_create_partner(request.user)
        credit_to_apply = min(credit_to_apply, partner.credit_balance, plan_price).quantize(Decimal('0.01'))
    else:
        credit_to_apply = Decimal('0')

    net_amount = max(plan_price - credit_to_apply, Decimal('0'))

    # Full credit cover — no Razorpay needed
    if net_amount == 0:
        return JsonResponse({'free': True, 'credit_used': str(credit_to_apply), 'plan_slug': plan_slug})

    amount_paise = int(net_amount * 100)
    if amount_paise < 100:
        return JsonResponse({'error': 'Amount too small for payment gateway'}, status=400)

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'plan_{plan_slug}_{request.user.id}',
        })
    except Exception as exc:
        logger.exception('Razorpay create_order failed: %s', exc)
        return JsonResponse({'error': 'Payment service error. Please try again.'}, status=500)

    return JsonResponse({
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'credit_used': str(credit_to_apply),
    })


@login_required
@require_POST
def verify_payment(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    payment_id = data.get('razorpay_payment_id', '')
    order_id = data.get('razorpay_order_id', '')
    signature = data.get('razorpay_signature', '')
    plan_slug = data.get('plan_slug', '')

    if not all([payment_id, order_id, signature, plan_slug]):
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    if plan_slug not in PLAN_PRICES:
        return JsonResponse({'error': 'Invalid plan'}, status=400)

    if not _verify_razorpay_signature(order_id, payment_id, signature):
        logger.warning('Razorpay signature mismatch for user %s order %s', request.user.id, order_id)
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    plan_days = 30 if plan_slug == 'test_plan' else 365
    plan_price = PLAN_PRICES[plan_slug]
    sub = get_or_create_subscription(request.user)
    sub.plan_slug = plan_slug
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = timezone.now() + timezone.timedelta(days=plan_days)
    sub.trial_ends_at = None
    sub.save()

    # Deduct partner credit if used
    credit_used = Decimal(str(data.get('credit_amount', 0) or 0)).quantize(Decimal('0.01'))
    if credit_used > 0:
        from apps.affiliates.services import get_or_create_partner, apply_partner_credit
        partner = get_or_create_partner(request.user)
        apply_partner_credit(partner, credit_used, plan_slug)

    # Credit referring partner for this purchase
    from apps.affiliates.services import credit_partner_for_plan
    credit_partner_for_plan(request.user, plan_slug, plan_price)

    label = PLAN_LABELS.get(plan_slug, plan_slug)
    logger.info('Payment verified — user %s upgraded to %s', request.user.id, plan_slug)
    return JsonResponse({'status': 'success', 'plan': plan_slug, 'label': label})


@login_required
@require_POST
def partner_credit_buy(request):
    """Activate a plan entirely with partner credit (no Razorpay payment)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    plan_slug = data.get('plan_slug', '')
    if plan_slug not in PLAN_PRICES:
        return JsonResponse({'error': 'Invalid plan'}, status=400)

    plan_price = PLAN_PRICES[plan_slug]

    from apps.affiliates.services import get_or_create_partner, apply_partner_credit
    partner = get_or_create_partner(request.user)
    if partner.credit_balance < plan_price:
        return JsonResponse({'error': 'Insufficient credit balance'}, status=400)

    apply_partner_credit(partner, plan_price, plan_slug)

    plan_days = 30 if plan_slug == 'test_plan' else 365
    sub = get_or_create_subscription(request.user)
    sub.plan_slug = plan_slug
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = timezone.now() + timezone.timedelta(days=plan_days)
    sub.trial_ends_at = None
    sub.save()

    label = PLAN_LABELS.get(plan_slug, plan_slug)
    logger.info('Partner credit buy — user %s activated %s for ₹%s credit', request.user.id, plan_slug, plan_price)
    return JsonResponse({'status': 'success', 'plan': plan_slug, 'label': label})


def _verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    msg = f'{order_id}|{payment_id}'.encode()
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@login_required
@require_POST
def verify_addon_payment(request):
    """Verify Razorpay payment and create a PlanAddon (does NOT replace base subscription)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    payment_id = data.get('razorpay_payment_id', '')
    order_id = data.get('razorpay_order_id', '')
    signature = data.get('razorpay_signature', '')
    plan_slug = data.get('plan_slug', '')

    if not all([payment_id, order_id, signature, plan_slug]):
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    if plan_slug not in PLAN_PRICES:
        return JsonResponse({'error': 'Invalid plan'}, status=400)

    if not _verify_razorpay_signature(order_id, payment_id, signature):
        logger.warning('Razorpay addon signature mismatch for user %s order %s', request.user.id, order_id)
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    plan_days = 30 if plan_slug == 'test_plan' else 365
    addon = PlanAddon.objects.create(
        user=request.user,
        plan_slug=plan_slug,
        status=PlanAddon.Status.ACTIVE,
        current_period_end=timezone.now() + timezone.timedelta(days=plan_days),
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
    )

    from .models import FLASK_LIMITS
    label = PLAN_LABELS.get(plan_slug, plan_slug)
    extra_sites = PLAN_LIMITS.get(plan_slug, 0)
    extra_flask = FLASK_LIMITS.get(plan_slug, 0)
    logger.info('Addon payment verified — user %s bought %s (+%s sites +%s flask)', request.user.id, plan_slug, extra_sites, extra_flask)
    return JsonResponse({
        'status': 'success',
        'plan': plan_slug,
        'label': label,
        'extra_sites': extra_sites,
        'extra_flask': extra_flask,
        'expires': addon.current_period_end.strftime('%d %b %Y'),
    })
