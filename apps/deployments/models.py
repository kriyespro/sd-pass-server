from django.db import models

from apps.projects.models import Project
from apps.uploads.models import ProjectUpload


class DeploymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'


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
