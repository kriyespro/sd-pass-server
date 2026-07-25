from django.db import models

from apps.projects.models import Project


class DrupalInstance(models.Model):
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='drupal_instance',
    )
    container_id = models.CharField(max_length=64, blank=True)
    admin_user = models.CharField(max_length=64, default='admin')
    admin_pass_enc = models.CharField(
        max_length=512, blank=True,
        help_text='Fernet ciphertext (same key as env vars). Blank when the uploaded '
                   'codebase already had its own sites/default/settings.php — the '
                   'platform never ran drush site:install for it and does not know its password.',
    )
    admin_email = models.EmailField(max_length=254)
    site_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Drupal · {self.project.slug}'
