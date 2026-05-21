from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView

from apps.billing.services import user_can_use_subfolder
from apps.deployments.services import MAX_STATIC_FILES_PER_POST, _validate_subfolder, save_static_files
from apps.logs.models import LogKind
from apps.logs.services import append_project_log
from apps.projects.models import Project, ProjectSubfolder, ProjectType

from .forms import MultiStaticUploadForm, ZipUploadForm
from .models import ProjectUpload
from .tasks import enqueue_upload_pipeline


def _site_url_hints(project: Project) -> dict:
    """Context vars for URL preview shown on upload forms."""
    base = (settings.STUDENT_APPS_BASE_DOMAIN or '').strip()
    scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http') or 'http'
    port = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0) or 0
    port_seg = f':{port}' if port else ''
    sub_base_url = f'{scheme}://{project.subdomain}.{base}{port_seg}/' if base else ''
    custom_base_url = ''
    if project.custom_hostname and project.custom_hostname_verified:
        custom_base_url = f'{scheme}://{project.custom_hostname}/'
    return {
        'sub_base_url': sub_base_url,
        'custom_base_url': custom_base_url,
        'deployed_subfolders': list(
            ProjectSubfolder.objects
            .filter(project=project)
            .order_by('path')
            .values_list('path', flat=True)
        ),
    }


def _friendly_static_upload_error(msg: str) -> str:
    if msg.startswith('disallowed_type:'):
        return f'File type not allowed: {msg.split(":", 1)[1]}'
    if msg.startswith('invalid_filename:'):
        return (
            'Each path must be relative (e.g. images/photo.png), stay inside the site folder, '
            'and must not use ..'
        )
    if msg.startswith('duplicate_path:'):
        return 'The same relative path appears twice in this upload (duplicate files).'
    if msg == 'path_too_deep':
        return 'Folder structure is too deep for this upload. Use a ZIP or fewer nested folders.'
    if msg == 'path_too_long':
        return 'A file path is too long. Shorten folder or file names, or use a ZIP upload.'
    if msg == 'no_files':
        return 'Select one or more files.'
    if msg == 'only_static_projects':
        return 'This action is only for Static projects.'
    if msg == 'total_size_exceeds_limit':
        return 'Total size of all files exceeds your upload limit.'
    if msg.startswith('max_'):
        return f'Too many files (maximum {MAX_STATIC_FILES_PER_POST} per request).'
    if msg == 'use_zip_upload_for_archives':
        return 'Do not upload .zip here — use the ZIP upload page for archives.'
    if msg == 'invalid_subfolder':
        return (
            'Subfolder must contain only letters, digits, hyphens, underscores, or / '
            '— no leading/trailing slashes or ..'
        )
    if msg.startswith('image_too_large:'):
        name = msg.split(':', 1)[1]
        return f'Image "{name}" exceeds 120 KB. Please compress it and re-upload.'
    return msg


class ZipUploadView(LoginRequiredMixin, CreateView):
    model = ProjectUpload
    form_class = ZipUploadForm
    template_name = 'pages/uploads/project_zip.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        ctx['recent_uploads'] = (
            ProjectUpload.objects.filter(project=self.project)
            .order_by('-created_at')[:10]
        )
        ctx['upload_max_mb'] = settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024)
        ctx['is_static_project'] = self.project.project_type == ProjectType.STATIC
        ctx.update(_site_url_hints(self.project))
        return ctx

    def form_valid(self, form):
        form.instance.project = self.project
        form.instance.owner = self.request.user
        uploaded = self.request.FILES.get('file')
        if not uploaded:
            form.add_error('file', 'Choose a ZIP file to upload.')
            return self.form_invalid(form)
        subfolder = self.request.POST.get('subfolder', '').strip()
        if subfolder and not user_can_use_subfolder(self.request.user):
            form.add_error(None, 'Subfolder deployment requires a paid plan. Upgrade to use this feature.')
            return self.form_invalid(form)
        sub_ok, _ = _validate_subfolder(subfolder)
        if not sub_ok:
            form.add_error(
                None,
                'Subfolder must contain only letters, digits, hyphens, underscores, or / '
                '— no leading/trailing slashes or ..',
            )
            return self.form_invalid(form)
        form.instance.original_name = uploaded.name
        form.instance.size_bytes = uploaded.size
        form.instance.deploy_subfolder = subfolder
        response = super().form_valid(form)
        enqueue_upload_pipeline.delay(self.object.pk)
        messages.success(
            self.request,
            'ZIP received. Security scan and deploy stub are running in the background.',
        )
        return response

    def get_success_url(self):
        return reverse_lazy('projects:dashboard')


class MultiStaticFilesView(LoginRequiredMixin, View):
    """Upload many static files for Static projects — flat files and/or a folder (preserves subpaths)."""

    template_name = 'pages/uploads/project_static_files.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        if self.project.project_type != ProjectType.STATIC:
            messages.warning(
                request,
                'Multi-file upload is only available when the project type is Static.',
            )
            return HttpResponseRedirect(reverse('projects:upload_zip', kwargs={'slug': self.project.slug}))
        return super().dispatch(request, *args, **kwargs)

    def _ctx(self, form=None):
        return {
            'project': self.project,
            'form': form or MultiStaticUploadForm(),
            'upload_max_mb': settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024),
            'max_files': MAX_STATIC_FILES_PER_POST,
            **_site_url_hints(self.project),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._ctx())

    def post(self, request, *args, **kwargs):
        form = MultiStaticUploadForm(request.POST)
        files = request.FILES.getlist('files')
        if not form.is_valid():
            return render(request, self.template_name, self._ctx(form), status=422)
        if not files:
            form.add_error(None, 'Select one or more files.')
            return render(request, self.template_name, self._ctx(form), status=422)
        subfolder = request.POST.get('subfolder', '').strip()
        if subfolder and not user_can_use_subfolder(request.user):
            form.add_error(None, 'Subfolder deployment requires a paid plan. Upgrade to use this feature.')
            return render(request, self.template_name, self._ctx(form), status=402)
        ok, msg = save_static_files(self.project, files, subfolder=subfolder)
        if not ok:
            form.add_error(None, _friendly_static_upload_error(msg))
            return render(request, self.template_name, self._ctx(form), status=422)
        # Persist the subfolder so the dashboard shows the correct site URL.
        normalised = subfolder.strip('/')
        Project.objects.filter(pk=self.project.pk).update(site_subfolder=normalised)
        ProjectSubfolder.objects.update_or_create(project=self.project, path=normalised)
        append_project_log(
            self.project,
            LogKind.BUILD,
            f'Multi-file static upload: {msg}',
        )
        messages.success(
            request,
            f'Saved {len(files)} file(s). Open your site host when index.html is present.',
        )
        return HttpResponseRedirect(reverse('projects:dashboard'))
