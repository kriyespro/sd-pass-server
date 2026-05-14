from django.conf import settings
from django.db import models


class Subscription(models.Model):
    class Plan(models.TextChoices):
        FREE = 'free', 'Free'
        PRO = 'pro', 'Pro'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAST_DUE = 'past_due', 'Past due'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan_slug = models.CharField(
        max_length=32,
        choices=Plan.choices,
        default=Plan.FREE,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    current_period_end = models.DateTimeField(null=True, blank=True)
    external_customer_id = models.CharField(max_length=255, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} · {self.plan_slug}'
