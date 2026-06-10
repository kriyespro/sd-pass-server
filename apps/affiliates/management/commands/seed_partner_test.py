"""
Seed partner test data on the superuser account.

Usage:
    python manage.py seed_partner_test                  # dry-run, shows what would happen
    python manage.py seed_partner_test --apply          # writes to DB
    python manage.py seed_partner_test --apply --reset  # wipes existing test data first

What it does:
  1. Gets/creates a Partner profile for the superuser.
  2. Simulates 3 fake user link clicks (increments click_count).
  3. Creates 3 fake referred users (test_ref_1@krizn.test etc.).
  4. Creates PartnerReferral rows for each (pending → credited).
  5. Calls credit_partner_for_plan for each to test slab + first-referral-bonus logic.
  6. Prints a full summary of the resulting state.

Fake users are created with is_active=False so they never appear in real dashboards.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

User = get_user_model()

FAKE_USERS = [
    {'email': 'test_ref_1@krizn.test', 'plan_slug': 'starter_cloud',   'amount': Decimal('2099.00')},
    {'email': 'test_ref_2@krizn.test', 'plan_slug': 'launch_lite',     'amount': Decimal('1499.00')},
    {'email': 'test_ref_3@krizn.test', 'plan_slug': 'business_cloud',  'amount': Decimal('5999.00')},
]


class Command(BaseCommand):
    help = 'Seed partner test data on the superuser for end-to-end testing'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to DB (default is dry-run)')
        parser.add_argument('--reset', action='store_true', help='Delete existing test referral rows first')

    def handle(self, *args, **options):
        apply = options['apply']
        reset = options['reset']

        superuser = User.objects.filter(is_superuser=True, is_active=True).order_by('date_joined').first()
        if not superuser:
            raise CommandError('No active superuser found. Create one first with createsuperuser.')

        self.stdout.write(f'\nSuperuser: {superuser.email} (id={superuser.pk})')
        self.stdout.write(f'Mode: {"APPLY (writing to DB)" if apply else "DRY-RUN (no writes)"}\n')

        if not apply:
            self._dry_run(superuser)
            return

        with transaction.atomic():
            self._run(superuser, reset)

    def _dry_run(self, superuser):
        from apps.affiliates.models import Partner, PartnerReferral, get_partner_slab
        from apps.affiliates.services import get_or_create_partner, FIRST_REFERRAL_BONUS_RATE

        self.stdout.write('--- What would happen ---\n')
        try:
            partner = superuser.partner_profile
            self.stdout.write(f'Partner code: {partner.code}')
            self.stdout.write(f'Current click_count: {partner.click_count}  → would become {partner.click_count + 3}')
            self.stdout.write(f'Current credit_balance: ₹{partner.credit_balance}')
        except Partner.DoesNotExist:
            self.stdout.write('Partner profile: NOT YET CREATED → would be created')

        self.stdout.write('\nFake referrals to create:')
        paid_so_far = 0
        for i, u in enumerate(FAKE_USERS):
            if paid_so_far == 0:
                rate = FIRST_REFERRAL_BONUS_RATE
                note = '← first referral bonus'
            else:
                rate, label = get_partner_slab(paid_so_far)
                note = f'← {label} slab'
            commission = (u['amount'] * rate).quantize(Decimal('0.01'))
            self.stdout.write(
                f'  [{i+1}] {u["email"]} · {u["plan_slug"]} · ₹{u["amount"]} '
                f'× {int(rate*100)}% = ₹{commission}  {note}'
            )
            paid_so_far += 1

        self.stdout.write('\nRun with --apply to write this data.')

    def _run(self, superuser, reset):
        from apps.affiliates.models import Partner, PartnerReferral, get_partner_slab
        from apps.affiliates.services import (
            get_or_create_partner, credit_partner_for_plan, FIRST_REFERRAL_BONUS_RATE,
        )
        from apps.billing.services import get_or_create_subscription

        partner = get_or_create_partner(superuser)
        self.stdout.write(f'Partner code: {partner.code}')

        if reset:
            deleted, _ = PartnerReferral.objects.filter(
                partner=partner,
                referred_user__email__endswith='@krizn.test',
            ).delete()
            User.objects.filter(email__endswith='@krizn.test').delete()
            self.stdout.write(f'Reset: deleted {deleted} referral rows + fake users.')
            partner.refresh_from_db()

        # Simulate 3 link clicks
        Partner.objects.filter(pk=partner.pk).update(
            click_count=partner.click_count + 3
        )
        partner.refresh_from_db()
        self.stdout.write(f'click_count now: {partner.click_count}')

        # Create fake users + referrals + credits
        for u in FAKE_USERS:
            fake_user, created = User.objects.get_or_create(
                email=u['email'],
                defaults={
                    'username': u['email'],
                    'is_active': False,
                    'first_name': f'Test',
                    'last_name': f'Ref {u["email"].split("_")[2].split("@")[0]}',
                },
            )
            get_or_create_subscription(fake_user)

            referral, ref_created = PartnerReferral.objects.get_or_create(
                partner=partner,
                referred_user=fake_user,
                defaults={'status': PartnerReferral.Status.PENDING},
            )

            if referral.status == PartnerReferral.Status.CREDITED:
                self.stdout.write(f'  {u["email"]}: already credited (skipping)')
                continue

            result = credit_partner_for_plan(fake_user, u['plan_slug'], u['amount'])
            if result:
                self.stdout.write(
                    f'  {u["email"]}: ₹{u["amount"]} × {int(result.commission_rate*100)}% '
                    f'= ₹{result.commission_amount} credited'
                )
            else:
                self.stdout.write(f'  {u["email"]}: credit_partner_for_plan returned None')

        partner.refresh_from_db()
        slab = partner.slab_info

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Partner state after seed ==='
            f'\nCode:           {partner.code}'
            f'\nClick count:    {partner.click_count}'
            f'\nTier:           {slab["label"]} ({slab["rate_pct"]}%)'
            f'\nPaid referrals: {slab["count"]}'
            f'\nTotal earned:   ₹{partner.total_earned}'
            f'\nCredit balance: ₹{partner.credit_balance}'
            f'\nTotal redeemed: ₹{partner.total_redeemed}'
        ))
        if slab['next']:
            self.stdout.write(f'Next tier:      {slab["next"]["need"]} more → {slab["next"]["label"]}')

        self.stdout.write(
            f'\nShare URL: /billing/redeem/?pref={partner.code}'
            f'\nPartner page: /partner/'
            f'\nAdmin: /admin/affiliates/partnerreferral/'
        )
