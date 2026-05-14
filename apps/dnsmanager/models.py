from django.conf import settings
from django.db import models

from apps.projects.models import Project


class DnsStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPLIED = 'applied', 'Applied'
    FAILED = 'failed', 'Failed'


class DnsRecord(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='dns_records',
        db_index=True,
    )
    fqdn = models.CharField(max_length=253)
    record_type = models.CharField(max_length=10, default='A')
    target_ip = models.CharField(max_length=45)
    cloudflare_record_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=DnsStatus.choices,
        default=DnsStatus.PENDING,
        db_index=True,
    )
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['project', 'fqdn'], name='dnsmanager_project_fqdn_uniq'),
        ]

    def __str__(self):
        return f'{self.fqdn} → {self.target_ip}'
