from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        _patch_create_permissions_safe()
        from django.db.models.signals import post_migrate

        def sync_site(sender, **kwargs):
            if sender.name != 'sites':
                return
            from django.conf import settings
            from django.contrib.sites.models import Site

            domain = getattr(settings, 'SITE_DOMAIN', '') or 'localhost:8000'
            name = getattr(settings, 'SITE_NAME', 'StudentCloud Deploy')
            Site.objects.update_or_create(
                pk=settings.SITE_ID,
                defaults={'domain': domain, 'name': name},
            )

        post_migrate.connect(sync_site, dispatch_uid='accounts_sync_site')


def _patch_create_permissions_safe():
    """
    Avoid migrate exit code 1 when auth permissions already exist (e.g. django-axes
    re-added after a partial deploy). Real migrations still apply; only duplicate
    permission inserts are skipped.
    """
    import django.contrib.auth.management as auth_mgmt
    from django.db import IntegrityError

    if getattr(auth_mgmt.create_permissions, '_sdpaas_safe', False):
        return

    _original = auth_mgmt.create_permissions

    def create_permissions_safe(*args, **kwargs):
        try:
            return _original(*args, **kwargs)
        except IntegrityError as exc:
            if 'auth_permission' not in str(exc) and 'permission' not in str(exc).lower():
                raise

    create_permissions_safe._sdpaas_safe = True
    auth_mgmt.create_permissions = create_permissions_safe
