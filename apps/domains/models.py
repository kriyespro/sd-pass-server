from django.conf import settings
from django.db import models

from apps.projects.models import Project


class RouteStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPLIED = 'applied', 'Applied'
    FAILED = 'failed', 'Failed'


class ProjectRoute(models.Model):
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='route',
    )
    fqdn = models.CharField(max_length=255)
    config_path = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=20,
        choices=RouteStatus.choices,
        default=RouteStatus.PENDING,
        db_index=True,
    )
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.fqdn} ({self.get_status_display()})'
