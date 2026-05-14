from django.contrib.auth import login
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import EmailAuthenticationForm, UserRegistrationForm


class RegisterView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'pages/register.jinja'
    success_url = reverse_lazy('projects:dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        from apps.billing.services import get_or_create_subscription

        get_or_create_subscription(self.object)
        return response


class LoginView(DjangoLoginView):
    template_name = 'pages/login.jinja'
    redirect_authenticated_user = True
    authentication_form = EmailAuthenticationForm
