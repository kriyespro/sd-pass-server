from django.conf import settings
from django.db import models


class UserOnboarding(models.Model):
    """Tracks first-time guided setup (name → project → upload → deploy)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='onboarding',
    )
    step_completed = models.PositiveSmallIntegerField(
        default=0,
        help_text='Last finished wizard step (1=name, 2=project, 3=upload).',
    )
    skipped = models.BooleanField(default=False)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Set after first successful deployment (or skip).',
    )

    class Meta:
        verbose_name = 'user onboarding'
        verbose_name_plural = 'user onboarding'

    def __str__(self):
        return f'Onboarding({self.user_id}, step={self.step_completed})'
