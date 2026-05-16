import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView
from django_htmx.http import HttpResponseClientRedirect

from apps.billing.services import user_project_limit
from apps.domains.services import write_project_router_file

from .forms import ProjectCustomHostnameForm, ProjectForm
from .models import Project
from .services import soft_delete_project
from .tasks import on_project_created

_STUDENT_APPS_IPV4 = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')


class ProjectDashboardView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'pages/projects/dashboard.jinja'
    context_object_name = 'projects'

    def get_queryset(self):
        return (
            Project.objects.filter(owner=self.request.user, is_deleted=False)
            .select_related('owner')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project_count'] = len(ctx['projects'])
        ctx['plan_limit'] = user_project_limit(self.request.user)
        from core.server_stats import get_server_stats
        ctx['server'] = get_server_stats()
        base = (settings.STUDENT_APPS_BASE_DOMAIN or '').strip()
        ctx['apps_base_domain'] = base
        ctx['student_apps_base_is_ipv4'] = bool(_STUDENT_APPS_IPV4.match(base))
        ctx['student_public_port'] = getattr(settings, 'STUDENT_PUBLIC_HTTP_PORT', 0) or 0
        ctx['student_site_port'] = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0) or 0
        ctx['student_site_scheme'] = getattr(
            settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http'
        )
        from apps.accounts.services import profile_is_complete
        from apps.onboarding.services import should_show_onboarding, sync_onboarding_progress
        from apps.onboarding.services import current_wizard_step as onboarding_current_step

        ctx['profile_complete'] = profile_is_complete(self.request.user)
        ctx['onboarding_active'] = should_show_onboarding(self.request.user)
        if ctx['onboarding_active']:
            ob = sync_onboarding_progress(self.request.user)
            ctx['onboarding'] = ob
            ctx['onboarding_step'] = onboarding_current_step(ob)
            ctx['onboarding_project'] = (
                Project.objects.filter(owner=self.request.user, is_deleted=False)
                .order_by('-created_at')
                .first()
            )
            from django.conf import settings as dj_settings
            from apps.deployments.services import MAX_STATIC_FILES_PER_POST

            ctx['upload_max_mb'] = dj_settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024)
            ctx['upload_max_files'] = MAX_STATIC_FILES_PER_POST
            ctx['upload_error'] = self.request.session.pop('onboarding_upload_error', None)
        return ctx


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'pages/projects/project_create.jinja'
    success_url = reverse_lazy('projects:dashboard')

    def _limit_reached(self):
        limit = user_project_limit(self.request.user)
        count = Project.objects.filter(owner=self.request.user, is_deleted=False).count()
        return count >= limit, limit

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            reached, limit = self._limit_reached()
            if reached:
                messages.warning(
                    request,
                    f'You have reached your project limit ({limit} website'
                    f'{"s" if limit != 1 else ""}). '
                    'Upgrade your plan with a coupon code to create more projects.',
                )
                return HttpResponseRedirect(reverse('billing:redeem'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        adjusted = getattr(form, 'subdomain_adjusted_from', '')
        try:
            response = super().form_valid(form)
        except IntegrityError:
            form.instance.subdomain = ''
            form.instance.slug = ''
            response = super().form_valid(form)
        on_project_created.delay(self.object.pk)
        try:
            write_project_router_file(self.object)
        except OSError as exc:
            messages.warning(
                self.request,
                f'Project was created, but Traefik could not write its route file ({exc}). '
                'Restart the web container (runs regenerate_traefik_routes) or fix volume permissions.',
            )
        if adjusted:
            messages.success(
                self.request,
                f'Project “{self.object.name}” was created. Subdomain “{adjusted}” was already '
                f'taken — we assigned “{self.object.subdomain}” instead.',
            )
        else:
            messages.success(
                self.request,
                f'Project “{self.object.name}” was created at {self.object.subdomain}.',
            )
        if self.request.htmx:
            return HttpResponseClientRedirect(self.get_success_url())
        return response

    def form_invalid(self, form):
        if self.request.htmx:
            return TemplateResponse(
                self.request,
                'partials/projects/_project_form_panel.jinja',
                self.get_context_data(form=form),
                status=422,
            )
        return super().form_invalid(form)


class ProjectDeleteView(LoginRequiredMixin, View):
    """Confirm and soft-delete a project (owner only)."""

    template_name = 'pages/projects/project_delete_confirm.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(
            request,
            self.template_name,
            {
                'project': self.project,
                'apps_base_domain': settings.STUDENT_APPS_BASE_DOMAIN,
            },
        )

    def post(self, request, *args, **kwargs):
        name = self.project.name
        ok, err = soft_delete_project(project=self.project, user=request.user)
        if not ok:
            if err == 'already_deleted':
                messages.info(request, 'This project was already removed.')
            else:
                messages.error(request, 'You cannot remove this project.')
            return HttpResponseRedirect(reverse('projects:dashboard'))
        messages.success(
            request,
            f'Project “{name}” was deleted. Site files and uploads for it were removed.',
        )
        return HttpResponseRedirect(reverse('projects:dashboard'))


class ProjectCustomDomainView(LoginRequiredMixin, View):
    """Set optional vanity hostname; Traefik + DNS instructions for Cloudflare."""

    template_name = 'pages/projects/project_domain.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self._render(request, ProjectCustomHostnameForm(instance=self.project))

    def post(self, request, *args, **kwargs):
        form = ProjectCustomHostnameForm(request.POST, instance=self.project)
        if not form.is_valid():
            return self._render(request, form, status=422)
        self.project = form.save()
        try:
            write_project_router_file(self.project)
        except OSError as exc:
            messages.warning(
                request,
                f'Domain saved, but the Traefik route file could not be written: {exc}',
            )
        else:
            if (self.project.custom_hostname or '').strip():
                if self.project.custom_hostname_verified:
                    messages.success(
                        request,
                        'Domain saved and verified. Traefik route updated (re-run route sync in prod if needed).',
                    )
                else:
                    messages.success(
                        request,
                        'Domain saved. Add the TXT record below, then use “Check verification”.',
                    )
            else:
                messages.success(request, 'Custom domain removed.')
        from apps.domains.tasks import verify_single_custom_domain

        if (self.project.custom_hostname or '').strip() and not self.project.custom_hostname_verified:
            verify_single_custom_domain.delay(self.project.pk)
        return HttpResponseRedirect(reverse('projects:domain', kwargs={'slug': self.project.slug}))

    def _render(self, request, form, status=200):
        from apps.domains.services import project_fqdn
        from apps.domains.verification import challenge_txt_fqdn

        fqdn = project_fqdn(self.project)
        ch = (self.project.custom_hostname or '').strip()
        challenge_fqdn = challenge_txt_fqdn(ch) if ch else ''
        return render(
            request,
            self.template_name,
            {
                'project': self.project,
                'form': form,
                'platform_fqdn': fqdn,
                'public_ip': getattr(settings, 'PLATFORM_PUBLIC_IP', '') or '',
                'apps_base_domain': settings.STUDENT_APPS_BASE_DOMAIN,
                'student_public_port': getattr(settings, 'STUDENT_PUBLIC_HTTP_PORT', 0) or 0,
                'challenge_txt_fqdn': challenge_fqdn,
                'challenge_token': (self.project.custom_domain_challenge_token or ''),
                'domain_verified': self.project.custom_hostname_verified,
            },
            status=status,
        )


class CustomDomainVerifyNowView(LoginRequiredMixin, View):
    """Queue a DNS TXT check for this project's custom hostname."""

    http_method_names = ['post']

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        from apps.domains.tasks import verify_single_custom_domain

        if not (self.project.custom_hostname or '').strip():
            messages.info(request, 'Save a public domain first.')
            return HttpResponseRedirect(reverse('projects:domain', kwargs={'slug': self.project.slug}))
        verify_single_custom_domain.delay(self.project.pk)
        messages.success(
            request,
            'Verification check queued. Wait a few seconds and refresh this page.',
        )
        return HttpResponseRedirect(reverse('projects:domain', kwargs={'slug': self.project.slug}))
