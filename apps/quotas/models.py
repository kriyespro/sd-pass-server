from django.conf import settings
from django.db import models

from apps.accounts.models import User


class QuotaUsage(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quota_usage_samples',
        db_index=True,
    )
    sampled_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ram_mb_used = models.PositiveIntegerField(default=0)
    cpu_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    disk_gb_used = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    projects_running = models.PositiveSmallIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-sampled_at']
        indexes = [
            models.Index(fields=['user', '-sampled_at']),
        ]

    def __str__(self):
        return f'{self.user.email} @ {self.sampled_at:%Y-%m-%d %H:%M}'
