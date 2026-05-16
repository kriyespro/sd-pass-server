from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from apps.domains.services import write_project_router_file
from apps.projects.models import Project
from apps.projects.tasks import on_project_created
from apps.uploads.models import ProjectUpload
from apps.uploads.tasks import enqueue_upload_pipeline

from .forms import OnboardingNameForm, OnboardingProjectForm, OnboardingZipForm
from .services import (
    advance_step,
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
        'onboarding_deploying': kwargs.pop(
            'onboarding_deploying',
            ob.step_completed >= 3 and ob.completed_at is None,
        ),
        'onboarding_project': project,
        'upload_max_mb': settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024),
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

        form = OnboardingZipForm(request.POST, request.FILES)
        if not form.is_valid():
            return _render_wizard(
                request,
                ob,
                onboarding_form=form,
                onboarding_project=project,
                onboarding_step=3,
            )

        uploaded = request.FILES.get('file')
        if not uploaded:
            form.add_error('file', 'Choose a ZIP file to upload.')
            return _render_wizard(
                request,
                ob,
                onboarding_form=form,
                onboarding_project=project,
                onboarding_step=3,
            )

        upload = ProjectUpload(
            project=project,
            owner=request.user,
            original_name=uploaded.name,
            size_bytes=uploaded.size,
        )
        upload.file = uploaded
        upload.save()
        enqueue_upload_pipeline.delay(upload.pk)
        advance_step(ob, 3)
        messages.success(
            request,
            'ZIP uploaded. Security scan and deploy are running — you will get an alert when your site is live.',
        )
        return _finish(request)


class OnboardingSkipView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        skip_onboarding(request.user)
        messages.info(request, 'Setup skipped. You can create a project anytime from the dashboard.')
        return _finish(request)
