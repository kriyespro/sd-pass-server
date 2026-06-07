from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, TemplateView

from apps.resell.models import ResellProduct

from .forms import AffiliateApplicationForm
from .models import AffiliateApplication, PRODUCT_COMMISSION_RATE, SERVER_COMMISSION_RATE
from .services import (
    affiliate_product_url,
    affiliate_store_url,
    get_active_affiliate,
    get_application_for_user,
)


class AffiliateHubView(LoginRequiredMixin, CreateView):
    form_class = AffiliateApplicationForm
    template_name = 'pages/affiliates/apply.jinja'
    success_url = reverse_lazy('affiliates:success')
    login_url = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        affiliate = get_active_affiliate(request.user)
        if affiliate:
            return redirect('affiliates:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        user = self.request.user
        initial = super().get_initial()
        name = user.get_full_name().strip() or user.email.split('@')[0]
        initial.setdefault('name', name)
        initial.setdefault('email', user.email)
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['application'] = get_application_for_user(self.request.user)
        ctx['product_commission_pct'] = int(PRODUCT_COMMISSION_RATE * 100)
        ctx['server_commission_pct'] = int(SERVER_COMMISSION_RATE * 100)
        return ctx

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.email = self.request.user.email
        return super().form_valid(form)


class AffiliateDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/affiliates/dashboard.jinja'
    login_url = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
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


def affiliate_success(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    return render(
        request,
        'pages/affiliates/success.jinja',
        {'application': get_application_for_user(request.user)},
    )
