from django.db import models

from apps.projects.models import Project


class BackupJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='backup_jobs',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    storage_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Backup {self.project.slug} {self.status}'
