import secrets
import string
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


PLAN_LIMITS = {
    'free':     1,
    'starter':  3,
    'pro':      5,
    'business': 10,
}

PLAN_PRICES = {
    'starter':  Decimal('1499.00'),
    'pro':      Decimal('2099.00'),
    'business': Decimal('3699.00'),
}

PLAN_LABELS = {
    'free':     'Free — 1 website',
    'starter':  'Starter — 3 websites · ₹1,499/year',
    'pro':      'Pro — 5 websites · ₹2,099/year',
    'business': 'Business — 10 websites · ₹3,699/year',
}


class Subscription(models.Model):
    class Plan(models.TextChoices):
        FREE     = 'free',     'Free'
        STARTER  = 'starter',  'Starter'
        PRO      = 'pro',      'Pro'
        BUSINESS = 'business', 'Business'

    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Active'
        PAST_DUE  = 'past_due',  'Past due'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan_slug = models.CharField(
        max_length=32,
        choices=Plan.choices,
        default=Plan.FREE,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    current_period_end = models.DateTimeField(null=True, blank=True)
    external_customer_id = models.CharField(max_length=255, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} · {self.plan_slug}'

    @property
    def is_active(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.current_period_end and self.current_period_end < timezone.now():
            return False
        return True

    @property
    def max_projects(self) -> int:
        if not self.is_active:
            return PLAN_LIMITS['free']
        return PLAN_LIMITS.get(self.plan_slug, PLAN_LIMITS['free'])

    @property
    def plan_label(self) -> str:
        return PLAN_LABELS.get(self.plan_slug, self.plan_slug)


def _generate_coupon_code() -> str:
    """Generate a readable 16-char coupon code like STUD-ABCD-1234-EFGH."""
    chars = string.ascii_uppercase + string.digits
    raw = ''.join(secrets.choice(chars) for _ in range(16))
    return '-'.join([raw[i:i+4] for i in range(0, 16, 4)])


class CouponCode(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    plan = models.CharField(
        max_length=32,
        choices=Subscription.Plan.choices,
        default=Subscription.Plan.STARTER,
    )
    valid_days = models.PositiveIntegerField(
        default=365,
        help_text='How many days this plan stays active after redemption.',
    )
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='redeemed_coupons',
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='If set, coupon cannot be used after this date (leave blank = never expires).',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_coupons',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = 'used' if self.used_by_id else 'available'
        return f'{self.code} [{self.plan}] {status}'

    @property
    def is_redeemable(self) -> bool:
        if not self.is_active:
            return False
        if self.used_by_id:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True
