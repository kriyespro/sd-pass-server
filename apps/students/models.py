from django.conf import settings
from django.db import models


class Batch(models.Model):
    name = models.CharField(max_length=200)
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='batches_led',
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='batches',
        blank=True,
    )
    requires_approval = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile',
    )
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_trainees',
    )
    mobile = models.CharField(max_length=32, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f'Profile of {self.user.email}'


class QuotaConfig(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quota_config',
    )
    ram_mb = models.PositiveIntegerField(default=512)
    cpu_cores = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    disk_gb = models.PositiveIntegerField(default=2)
    max_projects = models.PositiveIntegerField(default=3)

    def __str__(self):
        return f'Quota for {self.user.email}'
