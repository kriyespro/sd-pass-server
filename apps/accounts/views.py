from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import EmailAuthenticationForm, UserRegistrationForm


class AuthGatewayView(TemplateView):
    """Login / sign-up entry — Google primary; manual form only when SHOW_MANUAL_AUTH."""

    template_name = 'pages/auth_social.jinja'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mode = self.kwargs.get('mode', 'login')
        ctx['is_register'] = mode == 'register'
        if getattr(settings, 'SHOW_MANUAL_AUTH', False):
            if mode == 'register':
                ctx['register_form'] = UserRegistrationForm()
            else:
                ctx['login_form'] = EmailAuthenticationForm()
        return ctx


class RegisterView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'pages/register.jinja'
    success_url = reverse_lazy('projects:dashboard')

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, 'SHOW_MANUAL_AUTH', False):
            return redirect('accounts:register')
        return super().dispatch(request, *args, **kwargs)

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

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, 'SHOW_MANUAL_AUTH', False):
            return redirect('accounts:login')
        locked_msg = _axes_lockout_message(request)
        if locked_msg and request.method == 'POST':
            messages.error(request, locked_msg)
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        response = super().form_invalid(form)
        locked_msg = _axes_lockout_message(self.request)
        if locked_msg:
            messages.error(self.request, locked_msg)
        return response


def _axes_lockout_message(request) -> str:
    try:
        from axes.helpers import get_cool_off, is_already_locked

        credentials = {
            'username': request.POST.get('username', ''),
            'password': request.POST.get('password', ''),
        }
        if is_already_locked(request, credentials=credentials):
            cooloff = get_cool_off()
            if cooloff:
                minutes = max(1, int(cooloff.total_seconds() // 60))
                return (
                    f'Too many failed login attempts. Try again in about {minutes} minutes.'
                )
            return 'Too many failed login attempts. Please try again later.'
    except Exception:
        pass
    return ''
