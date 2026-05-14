from django.db import models

from apps.projects.models import Project


class DatabaseInstance(models.Model):
    class Engine(models.TextChoices):
        POSTGRES = 'postgres', 'PostgreSQL'
        REDIS = 'redis', 'Redis'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='database_instances',
    )
    engine = models.CharField(max_length=20, choices=Engine.choices, default=Engine.POSTGRES)
    name = models.CharField(max_length=64, help_text='Logical DB name')
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=5432)
    username = models.CharField(max_length=64, blank=True)
    password_encrypted = models.TextField(blank=True, help_text='Fernet ciphertext (same key as env vars)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'name'),
                name='databases_dbinstance_project_name_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.project.slug}/{self.name} ({self.engine})'
