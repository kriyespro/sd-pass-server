from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.students.models import QuotaConfig, StudentProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile_and_quota(sender, instance, created, **kwargs):
    if created:
        StudentProfile.objects.get_or_create(user=instance)
        QuotaConfig.objects.get_or_create(user=instance)
