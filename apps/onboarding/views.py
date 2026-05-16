from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View

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
        'onboarding_step': current_wizard_step(ob),
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
            return HttpResponse('')

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
            resp = _render_wizard(
                request, ob, onboarding_form=form, onboarding_step=1
            )
            resp.status_code = 422
            return resp
        form.save()
        advance_step(ob, 1)
        ob.refresh_from_db()
        messages.success(request, 'Profile saved.')
        if not getattr(request, 'htmx', False):
            return redirect('projects:dashboard')
        return _render_wizard(request, ob)

    def _step_project(self, request, ob):
        form = OnboardingProjectForm(request.POST, user=request.user)
        if not form.is_valid():
            resp = _render_wizard(
                request, ob, onboarding_form=form, onboarding_step=2
            )
            resp.status_code = 422
            return resp
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        on_project_created.delay(project.pk)
        try:
            write_project_router_file(project)
        except OSError:
            pass
        advance_step(ob, 2)
        ob.refresh_from_db()
        messages.success(request, f'Project “{project.name}” created — upload your site files next.')
        if not getattr(request, 'htmx', False):
            return redirect('projects:dashboard')
        return _render_wizard(request, ob, onboarding_project=project)

    def _step_upload(self, request, ob):
        project = (
            Project.objects.filter(owner=request.user, is_deleted=False)
            .order_by('-created_at')
            .first()
        )
        if not project:
            messages.warning(request, 'Create a project first.')
            if not getattr(request, 'htmx', False):
                return redirect('projects:dashboard')
            return _render_wizard(request, ob, onboarding_step=2)

        form = OnboardingZipForm(request.POST, request.FILES)
        if not form.is_valid():
            resp = _render_wizard(
                request,
                ob,
                onboarding_form=form,
                onboarding_project=project,
                onboarding_step=3,
            )
            resp.status_code = 422
            return resp

        uploaded = request.FILES.get('file')
        if not uploaded:
            form.add_error('file', 'Choose a ZIP file to upload.')
            resp = _render_wizard(
                request,
                ob,
                onboarding_form=form,
                onboarding_project=project,
                onboarding_step=3,
            )
            resp.status_code = 422
            return resp

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
        ob.refresh_from_db()
        messages.success(
            request,
            'ZIP uploaded. Security scan and deploy are running — you will get an alert when your site is live.',
        )
        if not getattr(request, 'htmx', False):
            return redirect('projects:dashboard')
        return _render_wizard(
            request, ob, onboarding_project=project, onboarding_deploying=True
        )


class OnboardingSkipView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        skip_onboarding(request.user)
        if getattr(request, 'htmx', False):
            return HttpResponse('')
        return redirect('projects:dashboard')
