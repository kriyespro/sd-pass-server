from django.db import models

from apps.projects.models import Project
from apps.uploads.models import ProjectUpload


class DeploymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'


class DjangoSuperadmin(models.Model):
    """
    Auto-generated Django admin login for a project, provisioned once on its
    first successful deploy and shown in Mission Control so the owner never
    has to type (and possibly mistype) credentials by hand. The identifier
    is always an email derived from the app's own slug, which sidesteps the
    USERNAME_FIELD-vs-"email login form" mismatch that silently breaks
    manually-entered superadmin accounts on projects where email doubles as
    the username. Password is Fernet-encrypted at rest (same scheme as
    DatabaseInstance.password_encrypted) so it can be redisplayed to the
    owner without re-running the reset.
    """
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='django_superadmin',
    )
    email = models.EmailField(max_length=254)
    password_encrypted = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.project.slug} superadmin ({self.email})'


class Deployment(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='deployments',
        db_index=True,
    )
    upload = models.ForeignKey(
        ProjectUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deployments',
    )
    status = models.CharField(
        max_length=20,
        choices=DeploymentStatus.choices,
        default=DeploymentStatus.PENDING,
        db_index=True,
    )
    log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Deploy {self.project.slug} {self.status}'
