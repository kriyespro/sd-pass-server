import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class ProjectType(models.TextChoices):
    STATIC = 'static', 'Static'
    DJANGO = 'django', 'Django'
    FLASK = 'flask', 'Flask'
    NODE = 'node', 'Node'
    PHP = 'php', 'PHP'
    WORDPRESS = 'wordpress', 'WordPress'
    MYSQL_ONLY = 'mysql_only', 'MySQL only'


class ProjectStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    BUILDING = 'building', 'Building'
    DEPLOYING = 'deploying', 'Deploying'
    RUNNING = 'running', 'Running'
    FAILED = 'failed', 'Failed'
    STOPPED = 'stopped', 'Stopped'
    SUSPENDED = 'suspended', 'Suspended'


class Project(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='projects',
        db_index=True,
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    project_type = models.CharField(
        max_length=32,
        choices=ProjectType.choices,
        default=ProjectType.STATIC,
        db_index=True,
    )
    subdomain = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PENDING,
        db_index=True,
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    custom_hostname = models.CharField(
        max_length=253,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text='Optional public hostname (e.g. www.example.com) for this project.',
    )
    custom_hostname_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text='True after DNS TXT challenge proves domain ownership.',
    )
    custom_domain_challenge_token = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text='Secret token the student publishes in a TXT record before routing goes live.',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        new_h = (self.custom_hostname or '').strip().lower().rstrip('.')
        old_h = ''
        if self.pk:
            row = Project.objects.filter(pk=self.pk).values_list('custom_hostname', flat=True).first()
            old_h = ((row or '') or '').strip().lower().rstrip('.')
        if new_h != old_h:
            self.custom_hostname_verified = False
            self.custom_domain_challenge_token = secrets.token_urlsafe(32) if new_h else ''
        elif new_h and not self.custom_hostname_verified and not self.custom_domain_challenge_token:
            self.custom_domain_challenge_token = secrets.token_urlsafe(32)
        if self.custom_hostname:
            self.custom_hostname = self.custom_hostname.strip().rstrip('.') or None

        if not self.slug:
            base = slugify(self.name) or 'project'
            candidate = base
            while Project.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base}-{uuid.uuid4().hex[:8]}'
            self.slug = candidate
        if not self.subdomain:
            self.subdomain = self.slug
        base_sub = self.subdomain
        sub = base_sub
        n = 1
        while Project.objects.filter(subdomain=sub).exclude(pk=self.pk).exists():
            sub = f'{base_sub}-{n}'
            n += 1
        self.subdomain = sub
        super().save(*args, **kwargs)
