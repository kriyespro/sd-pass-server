from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

from apps.projects.models import Project


class EnvVar(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='env_vars',
        db_index=True,
    )
    key = models.CharField(max_length=128)
    value_ciphertext = models.TextField()

    class Meta:
        ordering = ['key']
        constraints = [
            models.UniqueConstraint(fields=['project', 'key'], name='envvar_project_key_uniq'),
        ]

    def __str__(self):
        return f'{self.key} ({self.project.slug})'

    def set_plaintext(self, value: str) -> None:
        f = Fernet(settings.FERNET_KEY)
        self.value_ciphertext = f.encrypt(value.encode()).decode()

    def get_plaintext(self) -> str:
        f = Fernet(settings.FERNET_KEY)
        return f.decrypt(self.value_ciphertext.encode()).decode()
