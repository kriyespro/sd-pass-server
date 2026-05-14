from django.conf import settings
from django.core.files.storage import storages
from django.db import models

from apps.projects.models import Project


class UploadStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SCANNING = 'scanning', 'Scanning'
    CLEAN = 'clean', 'Clean'
    REJECTED = 'rejected', 'Rejected'


def upload_to(instance, filename):
    return f'{instance.project.owner_id}/{instance.project_id}/{filename}'


class ProjectUpload(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='uploads',
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_uploads',
        db_index=True,
    )
    file = models.FileField(
        upload_to=upload_to,
        max_length=500,
        storage=storages['student_uploads'],
    )
    original_name = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_name} ({self.project.slug})'
