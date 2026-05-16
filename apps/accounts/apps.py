from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
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
