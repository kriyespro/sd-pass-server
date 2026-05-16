from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView

from apps.backups.models import BackupJob
from apps.deployments.models import Deployment, DeploymentStatus
from apps.logs.models import LogEntry
from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectStatus, ProjectType
from apps.security.models import ScanReport
from apps.dashboard.trainer_access import is_trainer, trainee_users_queryset
from apps.envmanager.models import EnvVar
from apps.students.models import Batch
from apps.uploads.models import ProjectUpload, UploadStatus


def _student_website_rows():
    """One row per active project for Mission Control table."""
    from apps.billing.models import PLAN_LABELS, Subscription

    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.')
    scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'https') or 'https'
    if scheme not in ('http', 'https'):
        scheme = 'https'
    port = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0) or 0
    port_seg = f':{port}' if port else ''

    site_counts = dict(
        Project.objects.filter(is_deleted=False)
        .values('owner_id')
        .annotate(c=Count('id'))
        .values_list('owner_id', 'c')
    )
    subs = {s.user_id: s for s in Subscription.objects.all()}

    rows = []
    for p in (
        Project.objects.filter(is_deleted=False)
        .select_related('owner')
        .order_by('-created_at')
    ):
        owner = p.owner
        plan_slug = subs[owner.pk].plan_slug if owner.pk in subs else 'free'
        name = (owner.get_full_name() or '').strip() or owner.username or '—'
        fqdn = f'{p.subdomain}.{base}' if base else ''
        site_url = f'{scheme}://{fqdn}{port_seg}/' if fqdn else ''
        custom = (p.custom_hostname or '').strip()
        custom_url = f'{scheme}://{custom}/' if custom and p.custom_hostname_verified else ''

        rows.append({
            'project_name': p.name,
            'site_url': site_url,
            'custom_url': custom_url,
            'email': owner.email,
            'name': name,
            'mobile': owner.mobile or '—',
            'plan_slug': plan_slug,
            'plan_label': PLAN_LABELS.get(plan_slug, plan_slug.capitalize()),
            'site_count': site_counts.get(owner.pk, 0),
            'status': p.get_status_display(),
        })
    return rows


class StaffPlatformOverviewView(UserPassesTestMixin, TemplateView):
    template_name = 'pages/ops/platform_overview.jinja'
    raise_exception = True

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        ctx['user_count'] = User.objects.filter(is_active=True).count()
        ctx['project_count'] = Project.objects.filter(is_deleted=False).count()
        ctx['projects_running'] = Project.objects.filter(
            is_deleted=False, status='running'
        ).count()
        ctx['projects_failed'] = Project.objects.filter(
            is_deleted=False, status='failed'
        ).count()
        ctx['recent_scans'] = (
            ScanReport.objects.select_related('upload__project__owner')
            .order_by('-created_at')[:15]
        )
        ctx['recent_batches'] = (
            Batch.objects.select_related('trainer')
            .annotate(student_count=Count('students'))
            .order_by('-created_at')[:12]
        )
        return ctx


class SuperuserMonitorView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Full-platform snapshot at /admin/ for staff (Django model admin remains at /sd/).
    Requires is_staff — turn on “Staff status” (and optionally superuser) for your account in /sd/.
    """

    login_url = reverse_lazy('accounts:login')
    template_name = 'pages/admin_monitor/dashboard.jinja'
    raise_exception = False

    def test_func(self) -> bool:
        u = self.request.user
        return u.is_authenticated and u.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.warning(
                self.request,
                'The /admin/ monitor is only for staff. Ask a superuser to turn on “Staff status” for your user in Django admin (/sd/).',
            )
            return HttpResponseRedirect(reverse('home'))
        return super().handle_no_permission()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        now = timezone.now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        ctx['student_websites'] = _student_website_rows()

        ctx['user_total'] = User.objects.count()
        ctx['user_active'] = User.objects.filter(is_active=True).count()
        ctx['user_staff'] = User.objects.filter(is_staff=True).count()
        ctx['users_joined_week'] = User.objects.filter(date_joined__gte=week_ago).count()

        ctx['project_active'] = Project.objects.filter(is_deleted=False).count()
        ctx['project_deleted'] = Project.objects.filter(is_deleted=True).count()
        ctx['projects_running'] = Project.objects.filter(
            is_deleted=False, status=ProjectStatus.RUNNING
        ).count()
        ctx['projects_failed'] = Project.objects.filter(
            is_deleted=False, status=ProjectStatus.FAILED
        ).count()
        ctx['projects_custom_domain'] = Project.objects.filter(
            is_deleted=False, custom_hostname__isnull=False
        ).exclude(custom_hostname='').count()

        type_labels = dict(ProjectType.choices)
        ctx['projects_by_type'] = [
            {
                'key': row['project_type'],
                'label': type_labels.get(row['project_type'], row['project_type']),
                'c': row['c'],
            }
            for row in Project.objects.filter(is_deleted=False)
            .values('project_type')
            .annotate(c=Count('id'))
            .order_by('-c')
        ]

        ctx['upload_total'] = ProjectUpload.objects.count()
        ctx['upload_week_bytes'] = (
            ProjectUpload.objects.filter(created_at__gte=week_ago).aggregate(
                s=Sum('size_bytes')
            )['s']
            or 0
        )
        upload_labels = dict(UploadStatus.choices)
        ctx['upload_status_rows'] = [
            {
                'status': r['status'],
                'label': upload_labels.get(r['status'], r['status']),
                'c': r['c'],
            }
            for r in ProjectUpload.objects.values('status')
            .annotate(c=Count('id'))
            .order_by('status')
        ]
        ctx['uploads_pending'] = ProjectUpload.objects.filter(
            status__in=(UploadStatus.PENDING, UploadStatus.SCANNING)
        ).count()

        ctx['logs_day'] = LogEntry.objects.filter(created_at__gte=day_ago).count()
        ctx['logs_week'] = LogEntry.objects.filter(created_at__gte=week_ago).count()

        ctx['notifications_unread'] = Notification.objects.filter(read_at__isnull=True).count()

        ctx['deployments_failed_week'] = Deployment.objects.filter(
            created_at__gte=week_ago, status=DeploymentStatus.FAILED
        ).count()
        ctx['backups_running'] = BackupJob.objects.filter(status=BackupJob.Status.RUNNING).count()

        ctx['recent_uploads'] = (
            ProjectUpload.objects.filter(project__is_deleted=False)
            .select_related('project', 'owner')
            .order_by('-created_at')[:20]
        )
        ctx['recent_logs'] = (
            LogEntry.objects.filter(project__is_deleted=False)
            .select_related('project', 'project__owner')
            .order_by('-created_at')[:30]
        )
        ctx['recent_scans'] = (
            ScanReport.objects.select_related('upload__project', 'upload__project__owner')
            .order_by('-created_at')[:18]
        )
        ctx['recent_users'] = User.objects.order_by('-date_joined')[:12]
        ctx['recent_projects'] = (
            Project.objects.filter(is_deleted=False)
            .select_related('owner')
            .order_by('-created_at')[:14]
        )
        ctx['recent_deployments'] = (
            Deployment.objects.select_related('project', 'upload')
            .order_by('-created_at')[:12]
        )

        # Server health
        from core.server_stats import get_server_stats
        ctx['server'] = get_server_stats()

        # Billing / subscription stats
        from apps.billing.models import PLAN_LIMITS, CouponCode, Subscription
        ctx['sub_total'] = Subscription.objects.count()
        ctx['sub_by_plan'] = list(
            Subscription.objects.values('plan_slug')
            .annotate(c=Count('id'))
            .order_by('-c')
        )
        for row in ctx['sub_by_plan']:
            row['limit'] = PLAN_LIMITS.get(row['plan_slug'], 1)
        ctx['coupons_available'] = CouponCode.objects.filter(
            is_active=True, used_by__isnull=True
        ).count()
        ctx['coupons_used'] = CouponCode.objects.filter(used_by__isnull=False).count()

        return ctx


class TrainerOverviewView(UserPassesTestMixin, TemplateView):
    template_name = 'pages/trainer/overview.jinja'
    raise_exception = True

    def test_func(self):
        return is_trainer(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        ctx['trainer_batches'] = (
            Batch.objects.filter(trainer=u)
            .annotate(student_count=Count('students'))
            .order_by('-created_at')
        )
        return ctx


class TrainerEnvAuditListView(UserPassesTestMixin, TemplateView):
    """Lists trainee projects with env var counts; values are never exposed."""

    template_name = 'pages/trainer/env_audit_list.jinja'
    raise_exception = True

    def test_func(self):
        return is_trainer(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        trainees = trainee_users_queryset(self.request.user)
        ctx['audit_projects'] = (
            Project.objects.filter(owner__in=trainees, is_deleted=False)
            .select_related('owner')
            .annotate(env_key_count=Count('env_vars'))
            .order_by('owner__email', 'name')
        )
        return ctx


class TrainerProjectEnvKeysView(UserPassesTestMixin, TemplateView):
    """Key names only for one trainee-owned project (404 if not supervised)."""

    template_name = 'pages/trainer/env_project_keys.jinja'
    raise_exception = True

    def test_func(self):
        return is_trainer(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        trainees = trainee_users_queryset(request.user)
        self.project = get_object_or_404(
            Project.objects.select_related('owner'),
            slug=kwargs['slug'],
            is_deleted=False,
            owner__in=trainees,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        ctx['env_keys'] = list(
            EnvVar.objects.filter(project=self.project)
            .order_by('key')
            .values_list('key', flat=True)
        )
        return ctx
