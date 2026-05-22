from django.core.management.base import BaseCommand

from apps.platform_ops.services.image_compression import backfill_missing_image_logs


class Command(BaseCommand):
    help = 'Queue image compression for static sites with images but no ImageCompressionLog yet.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Max projects to queue (default 50)',
        )

    def handle(self, *args, **options):
        n = backfill_missing_image_logs(limit=options['limit'])
        self.stdout.write(
            self.style.SUCCESS(f'Queued image compression for {n} project(s). Check Mission Control.')
        )
