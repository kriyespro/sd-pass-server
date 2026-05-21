import hashlib
import hmac
import json
import logging

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

from .models import PLAN_LABELS, PLAN_LIMITS, PLAN_PRICES, Subscription
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
        ctx['plans'] = [
            {
                'slug': 'test_plan',
                'name': 'Starter Trial',
                'subtitle': 'India · 1 Website · Custom Domain · 9 Days',
                'sites': '1',
                'price': '₹99',
                'period': '9 days',
                'specs': '1 website · Custom domain · Upgrade anytime · Suspends after 9 days',
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
                'subtitle': 'India · 1 Website',
                'sites': '1',
                'price': '₹3,699',
                'period': 'year',
                'specs': '2 GB RAM · 2 vCPU · 30 GB SSD',
                'highlight': False,
            },
            {
                'slug': 'business_cloud',
                'name': 'Business Cloud',
                'subtitle': 'India · 5 Websites',
                'sites': '5',
                'price': '₹5,999',
                'period': 'year',
                'specs': '4 GB RAM · 2 vCPU · 60 GB SSD',
                'highlight': True,
            },
            {
                'slug': 'agency_turbo',
                'name': 'Agency Turbo',
                'subtitle': 'USA · 10 Websites',
                'sites': '10',
                'price': '₹8,499',
                'period': 'year',
                'specs': '6 GB RAM · 4 vCPU · 80 GB NVMe SSD',
                'highlight': False,
            },
            {
                'slug': 'performance_max',
                'name': 'Performance Max',
                'subtitle': 'USA · Unlimited Websites',
                'sites': 'Unlimited',
                'price': '₹11,999',
                'period': 'year',
                'specs': '6 GB RAM · 4 vCPU · 120 GB NVMe SSD',
                'highlight': False,
            },
        ]
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

    amount_paise = int(PLAN_PRICES[plan_slug] * 100)
    if amount_paise < 100:
        return JsonResponse({'error': 'Amount too small'}, status=400)

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

    msg = f'{order_id}|{payment_id}'.encode()
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning('Razorpay signature mismatch for user %s order %s', request.user.id, order_id)
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    plan_days = 9 if plan_slug == 'test_plan' else 365
    sub = get_or_create_subscription(request.user)
    sub.plan_slug = plan_slug
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = timezone.now() + timezone.timedelta(days=plan_days)
    sub.save()

    label = PLAN_LABELS.get(plan_slug, plan_slug)
    logger.info('Payment verified — user %s upgraded to %s', request.user.id, plan_slug)
    return JsonResponse({'status': 'success', 'plan': plan_slug, 'label': label})
