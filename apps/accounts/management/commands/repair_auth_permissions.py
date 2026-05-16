"""
Remove duplicate auth.Permission rows and duplicate axes ContentTypes.

Run once on production if migrate fails with:
  duplicate key value violates unique constraint auth_permission_..._uniq

Usage:
  python manage.py repair_auth_permissions
"""
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Count


class Command(BaseCommand):
    help = 'Deduplicate auth permissions and axes content types (safe to re-run).'

    def handle(self, *args, **options):
        removed_perms = 0
        dup_groups = (
            Permission.objects.values('content_type_id', 'codename')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
        )
        for group in dup_groups:
            perms = list(
                Permission.objects.filter(
                    content_type_id=group['content_type_id'],
                    codename=group['codename'],
                ).order_by('id')
            )
            for perm in perms[1:]:
                perm.delete()
                removed_perms += 1

        removed_ct = 0
        for model in (
            'accessattempt',
            'accesslog',
            'accessfailurelog',
            'accessattemptexpiration',
        ):
            cts = list(
                ContentType.objects.filter(app_label='axes', model=model).order_by('pk')
            )
            if len(cts) <= 1:
                continue
            keep = cts[0]
            for dup in cts[1:]:
                Permission.objects.filter(content_type=dup).delete()
                dup.delete()
                removed_ct += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Removed {removed_perms} duplicate permission(s) '
                f'and {removed_ct} duplicate axes content type(s).'
            )
        )
        self.stdout.write('Run: python manage.py migrate')
