from django.core.management.base import BaseCommand

from apps.emails.services import process_due_campaigns


class Command(BaseCommand):
    help = 'Send all due email campaigns. Run via cron: */30 * * * * python manage.py run_email_campaigns'

    def handle(self, *args, **options):
        total = process_due_campaigns()
        self.stdout.write(self.style.SUCCESS(f'Campaigns processed. {total} email(s) sent.'))
