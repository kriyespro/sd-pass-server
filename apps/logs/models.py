from django.db import models

from apps.projects.models import Project


class LogKind(models.TextChoices):
    BUILD = 'build', 'Build'
    RUNTIME = 'runtime', 'Runtime'
    SYSTEM = 'system', 'System'


class LogEntry(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='log_entries',
        db_index=True,
    )
    kind = models.CharField(
        max_length=16,
        choices=LogKind.choices,
        default=LogKind.SYSTEM,
        db_index=True,
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
        ]

    def __str__(self):
        return f'{self.kind}@{self.created_at:%Y-%m-%d}'
