from django.db import models

from apps.uploads.models import ProjectUpload


class ScanStatus(models.TextChoices):
    CLEAN = 'clean', 'Clean'
    QUARANTINED = 'quarantined', 'Quarantined'
    REJECTED = 'rejected', 'Rejected'


class ScanReport(models.Model):
    upload = models.OneToOneField(
        ProjectUpload,
        on_delete=models.CASCADE,
        related_name='scan_report',
    )
    status = models.CharField(
        max_length=20,
        choices=ScanStatus.choices,
        db_index=True,
    )
    summary = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Scan {self.upload_id} {self.status}'
