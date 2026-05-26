from django.shortcuts import render
from django.views.generic import CreateView
from django.urls import reverse_lazy

from .forms import AffiliateApplicationForm


class AffiliateApplyView(CreateView):
    form_class = AffiliateApplicationForm
    template_name = 'pages/affiliates/apply.jinja'
    success_url = reverse_lazy('affiliates:success')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx


def affiliate_success(request):
    return render(request, 'pages/affiliates/success.jinja')
