from django.conf import settings
from django.db import models


class AssetOptimizationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)

    sites_scanned = models.PositiveIntegerField(
        default=0,
        help_text='Static sites with any files on disk',
    )
    projects_processed = models.PositiveIntegerField(
        default=0,
        help_text='Sites that contained CSS, JS, or images',
    )
    css_files = models.PositiveIntegerField(default=0)
    js_files = models.PositiveIntegerField(default=0)
    image_files = models.PositiveIntegerField(default=0)
    files_optimized = models.PositiveIntegerField(default=0)
    bytes_before = models.BigIntegerField(default=0)
    bytes_after = models.BigIntegerField(default=0)
    bytes_saved = models.BigIntegerField(default=0)

    cache_used_memory_human = models.CharField(max_length=64, blank=True)
    cache_peak_memory_human = models.CharField(max_length=64, blank=True)
    cache_keys = models.PositiveIntegerField(default=0)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asset_optimization_runs',
    )
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'AssetOptimizationRun #{self.pk} {self.status}'


class PlatformBackup(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    class BackupType(models.TextChoices):
        FULL = 'full', 'Full (database + sites)'
        DATABASE = 'database', 'Database only'
        SITES = 'sites', 'Student sites only'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    backup_type = models.CharField(
        max_length=20,
        choices=BackupType.choices,
        default=BackupType.FULL,
    )
    storage_path = models.CharField(max_length=500, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    includes_database = models.BooleanField(default=True)
    includes_sites = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_backups',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PlatformBackup #{self.pk} {self.backup_type} {self.status}'

    @property
    def filename(self):
        import os

        return os.path.basename(self.storage_path) if self.storage_path else ''
