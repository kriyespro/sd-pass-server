from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.projects.host_allowlist import invalidate_custom_host_cache

from .models import Project


@receiver(pre_save, sender=Project)
def _project_stash_custom_hostname(sender, instance, **kwargs):
    if not instance.pk:
        instance._prev_custom_hostname = None
        return
    try:
        prev = Project.objects.only('custom_hostname').get(pk=instance.pk)
        instance._prev_custom_hostname = prev.custom_hostname
    except Project.DoesNotExist:
        instance._prev_custom_hostname = None


@receiver(post_save, sender=Project)
def _project_clear_host_cache(sender, instance, **kwargs):
    invalidate_custom_host_cache(getattr(instance, '_prev_custom_hostname', None))
    invalidate_custom_host_cache(instance.custom_hostname)


@receiver(post_delete, sender=Project)
def _project_deleted_clear_host_cache(sender, instance, **kwargs):
    invalidate_custom_host_cache(instance.custom_hostname)
