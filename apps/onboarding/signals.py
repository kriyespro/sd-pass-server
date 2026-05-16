from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserOnboarding


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_onboarding(sender, instance, created, **kwargs):
    if created:
        UserOnboarding.objects.get_or_create(user=instance)
