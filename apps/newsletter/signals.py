from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_new_user_to_newsletter(sender, instance, created, **kwargs):
    if not created:
        return
    if not getattr(settings, 'SYSTEME_IO_API_KEY', ''):
        return
    from .services import sync_user
    try:
        sync_user(instance.email, instance.first_name, instance.last_name)
    except Exception:
        pass
