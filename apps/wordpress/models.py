from django.db import models

from apps.projects.models import Project


class WordPressInstance(models.Model):
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='wordpress_instance',
    )
    container_id = models.CharField(max_length=64, blank=True)
    wp_admin_user = models.CharField(max_length=64, default='admin')
    wp_admin_pass_enc = models.CharField(max_length=512, help_text='Fernet ciphertext (same key as env vars)')
    wp_admin_email = models.EmailField(max_length=254)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'WordPress · {self.project.slug}'
