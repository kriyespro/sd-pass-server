from django.conf import settings
from django.db import models


class NotificationLevel(models.TextChoices):
    INFO = 'info', 'Info'
    SUCCESS = 'success', 'Success'
    WARNING = 'warning', 'Warning'
    ERROR = 'error', 'Error'


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True,
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    level = models.CharField(
        max_length=16,
        choices=NotificationLevel.choices,
        default=NotificationLevel.INFO,
        db_index=True,
    )
    link_url = models.CharField(max_length=500, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'read_at']),
        ]

    def __str__(self):
        return f'{self.user_id} {self.title[:40]}'
