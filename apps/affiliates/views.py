import urllib.parse

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.billing.models import PLAN_LABELS, PLAN_PRICES
from apps.resell.models import ResellProduct

from .forms import AffiliateApplicationForm
from .models import PRODUCT_COMMISSION_RATE, SERVER_COMMISSION_RATE
from .services import (
    affiliate_product_url,
    affiliate_store_url,
    get_active_affiliate,
    get_application_for_user,
    get_or_create_partner,
    partner_share_url,
)


class AffiliateHubView(View):
    """Public program page; apply form requires login. Active affiliates see dashboard inline."""

    template_name = 'pages/affiliates/apply.jinja'
    dashboard_template_name = 'pages/affiliates/dashboard.jinja'

    def get(self, request):
        if request.user.is_authenticated:
            affiliate = get_active_affiliate(request.user)
            if affiliate:
                return render(request, self.dashboard_template_name, self._dashboard_context(request, affiliate))
        return render(request, self.template_name, self._context(request))

    def _dashboard_context(self, request, affiliate):
        products = ResellProduct.objects.filter(is_active=True).order_by('-is_featured', 'name')
        return {
            'affiliate': affiliate,
            'store_url': affiliate_store_url(request, affiliate),
            'product_links': [
                {
                    'product': product,
                    'url': affiliate_product_url(request, affiliate, product),
                }
                for product in products
            ],
            'commissions': affiliate.commissions.select_related('order').order_by('-created_at')[:25],
            'product_commission_pct': int(PRODUCT_COMMISSION_RATE * 100),
            'server_commission_pct': int(SERVER_COMMISSION_RATE * 100),
        }

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect_to_login(
                reverse('affiliates:apply'),
                login_url=str(reverse_lazy('accounts:login')),
            )
        form = AffiliateApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            application.email = request.user.email
            application.save()
            return redirect('affiliates:success')
        return render(request, self.template_name, self._context(request, form=form))

    def _context(self, request, form=None):
        user = request.user
        initial = {}
        if user.is_authenticated:
            name = user.get_full_name().strip() or user.email.split('@')[0]
            initial = {'name': name, 'email': user.email}
        return {
            'form': form or AffiliateApplicationForm(initial=initial),
            'application': get_application_for_user(user) if user.is_authenticated else None,
            'can_apply': user.is_authenticated,
            'login_url': f"{reverse('accounts:login')}?next={reverse('affiliates:apply')}",
            'product_commission_pct': int(PRODUCT_COMMISSION_RATE * 100),
            'server_commission_pct': int(SERVER_COMMISSION_RATE * 100),
        }


class AffiliateDashboardView(TemplateView):
    template_name = 'pages/affiliates/dashboard.jinja'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                reverse('affiliates:dashboard'),
                login_url=str(reverse_lazy('accounts:login')),
            )
        if not get_active_affiliate(request.user):
            return redirect('affiliates:apply')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        affiliate = get_active_affiliate(self.request.user)
        products = ResellProduct.objects.filter(is_active=True).order_by('-is_featured', 'name')
        ctx.update({
            'affiliate': affiliate,
            'store_url': affiliate_store_url(self.request, affiliate),
            'product_links': [
                {
                    'product': product,
                    'url': affiliate_product_url(self.request, affiliate, product),
                }
                for product in products
            ],
            'commissions': affiliate.commissions.select_related('order').order_by('-created_at')[:25],
            'product_commission_pct': int(PRODUCT_COMMISSION_RATE * 100),
            'server_commission_pct': int(SERVER_COMMISSION_RATE * 100),
        })
        return ctx


class PartnerPageView(LoginRequiredMixin, View):
    template_name = 'pages/affiliates/partner.jinja'

    def get(self, request):
        partner = get_or_create_partner(request.user)
        share_url = partner_share_url(request, partner)
        wa_text = urllib.parse.quote(
            f'Join Krizn — deploy your website in minutes! Sign up using my link: {share_url}',
            safe='',
        )
        wa_url = f'https://wa.me/?text={wa_text}'

        # Plans available for credit redemption
        redeemable_plans = [
            {
                'slug': slug,
                'label': PLAN_LABELS.get(slug, slug),
                'price': float(price),
                'affordable': partner.credit_balance >= price,
                'partial': 0 < partner.credit_balance < price,
            }
            for slug, price in PLAN_PRICES.items()
            if slug != 'free'
        ]

        return render(request, self.template_name, {
            'partner': partner,
            'share_url': share_url,
            'wa_url': wa_url,
            'slab_info': partner.slab_info,
            'referrals': partner.referrals.select_related('referred_user').order_by('-created_at')[:25],
            'redemptions': partner.redemptions.order_by('-created_at')[:10],
            'redeemable_plans': redeemable_plans,
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        })


def affiliate_success(request):
    if not request.user.is_authenticated:
        return redirect_to_login(
            reverse('affiliates:success'),
            login_url=str(reverse_lazy('accounts:login')),
        )
    return render(
        request,
        'pages/affiliates/success.jinja',
        {'application': get_application_for_user(request.user)},
    )
