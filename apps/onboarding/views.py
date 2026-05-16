from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from apps.deployments.services import MAX_STATIC_FILES_PER_POST, save_static_files
from apps.domains.services import write_project_router_file
from apps.logs.models import LogKind
from apps.logs.services import append_project_log
from apps.projects.models import Project
from apps.projects.tasks import on_project_created
from apps.uploads.views import _friendly_static_upload_error

from .forms import OnboardingNameForm, OnboardingProjectForm
from .services import (
    advance_step,
    complete_onboarding,
    current_wizard_step,
    should_show_onboarding,
    skip_onboarding,
    sync_onboarding_progress,
)


def _is_htmx(request) -> bool:
    return getattr(request, 'htmx', False)


def _finish(request):
    """After a wizard step: full-page refresh shows the next step + messages."""
    if _is_htmx(request):
        return HttpResponseClientRedirect(reverse('projects:dashboard'))
    return redirect('projects:dashboard')


def _is_xhr_upload(request) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _upload_error_response(request, ob, project, upload_error: str):
    """XHR: return wizard HTML (422). Browser POST: redirect to dashboard with error."""
    ctx = _wizard_context_fixed(
        request,
        ob,
        onboarding_project=project,
        onboarding_step=3,
        upload_error=upload_error,
    )
    if _is_xhr_upload(request):
        return render(
            request,
            'partials/onboarding/_wizard_modal.jinja',
            ctx,
            status=422,
        )
    request.session['onboarding_upload_error'] = upload_error
    return redirect('projects:dashboard')


def _wizard_context_fixed(request, ob, **kwargs):
    from django.conf import settings

    project = kwargs.pop('onboarding_project', None)
    if project is None:
        project = (
            Project.objects.filter(owner=request.user, is_deleted=False)
            .order_by('-created_at')
            .first()
        )
    ctx = {
        'onboarding': ob,
        'onboarding_step': kwargs.pop('onboarding_step', None) or current_wizard_step(ob),
        'onboarding_project': project,
        'upload_max_mb': settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024),
        'upload_max_files': MAX_STATIC_FILES_PER_POST,
    }
    ctx.update(kwargs)
    return ctx


def _render_wizard(request, ob, **kwargs):
    return render(
        request,
        'partials/onboarding/_wizard_modal.jinja',
        _wizard_context_fixed(request, ob, **kwargs),
    )


class OnboardingWizardPartialView(LoginRequiredMixin, View):
    """GET — render modal HTML for HTMX refresh."""

    def get(self, request):
        if not should_show_onboarding(request.user):
            return HttpResponse('')
        ob = sync_onboarding_progress(request.user)
        project = (
            Project.objects.filter(owner=request.user, is_deleted=False)
            .order_by('-created_at')
            .first()
        )
        return _render_wizard(request, ob, onboarding_project=project)


class OnboardingStepView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, step: int):
        if not should_show_onboarding(request.user):
            return _finish(request)

        ob = sync_onboarding_progress(request.user)
        step = int(step)

        if step == 1:
            return self._step_name(request, ob)
        if step == 2:
            return self._step_project(request, ob)
        if step == 3:
            return self._step_upload(request, ob)
        return HttpResponse('', status=404)

    def _step_name(self, request, ob):
        form = OnboardingNameForm(request.POST, instance=request.user)
        if not form.is_valid():
            return _render_wizard(
                request, ob, onboarding_form=form, onboarding_step=1
            )
        form.save()
        advance_step(ob, 1)
        messages.success(request, 'Profile saved.')
        return _finish(request)

    def _step_project(self, request, ob):
        form = OnboardingProjectForm(request.POST, user=request.user)
        if not form.is_valid():
            return _render_wizard(
                request, ob, onboarding_form=form, onboarding_step=2
            )
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        on_project_created.delay(project.pk)
        try:
            write_project_router_file(project)
        except OSError:
            pass
        advance_step(ob, 2)
        messages.success(
            request,
            f'Project “{project.name}” created — upload your site files next.',
        )
        return _finish(request)

    def _step_upload(self, request, ob):
        project = (
            Project.objects.filter(owner=request.user, is_deleted=False)
            .order_by('-created_at')
            .first()
        )
        if not project:
            messages.warning(request, 'Create a project first.')
            return _finish(request)

        files = request.FILES.getlist('files')
        if not files:
            return _upload_error_response(
                request,
                ob,
                project,
                'Select at least one file or image, or choose a project folder.',
            )

        ok, msg = save_static_files(project, files)
        if not ok:
            return _upload_error_response(
                request,
                ob,
                project,
                _friendly_static_upload_error(msg),
            )

        append_project_log(
            project,
            LogKind.BUILD,
            f'Onboarding file upload: {msg}',
        )
        advance_step(ob, 3)
        complete_onboarding(request.user)
        messages.success(
            request,
            f'Uploaded {len(files)} file(s). Open your live site from the dashboard when index.html is in place.',
        )
        return _finish(request)


class OnboardingSkipView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        skip_onboarding(request.user)
        messages.info(request, 'Setup skipped. You can create a project anytime from the dashboard.')
        return _finish(request)
