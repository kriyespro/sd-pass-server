from django.core.management.base import BaseCommand

from apps.platform_ops.services.asset_runner import run_asset_optimization


class Command(BaseCommand):
    help = 'Minify CSS/JS and optimize images on all active student static sites.'

    def handle(self, *args, **options):
        run = run_asset_optimization()
        self.stdout.write(
            self.style.SUCCESS(
                f'Done: {run.projects_processed} site(s), '
                f'{run.files_optimized} file(s) optimized, '
                f'{run.bytes_saved} bytes saved ({run.status}).'
            )
        )
