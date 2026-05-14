from django.db import models


class PlatformTlsConfig(models.Model):
    """Singleton-style row for Traefik ACME / cert resolver hints (admin-managed)."""

    name = models.SlugField(max_length=64, default='default', unique=True)
    acme_contact_email = models.EmailField(blank=True)
    cert_resolver_name = models.CharField(max_length=64, default='letsencrypt')
    traefik_acme_json_path = models.CharField(
        max_length=255,
        blank=True,
        help_text='Server path to acme.json (chmod 600). Documented for ops; not used by Django yet.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'platform TLS / ACME'
        verbose_name_plural = 'platform TLS / ACME'

    def __str__(self):
        return self.name
