import secrets
import string
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


PLAN_LIMITS = {
    'free':            1,
    'launch_lite':     1,
    'starter_cloud':   1,
    'wordpress_pro':   1,
    'business_cloud':  5,
    'agency_turbo':    10,
    'performance_max': 999,
}

FREE_TRIAL_DAYS = 7

PLAN_PRICES = {
    'launch_lite':     Decimal('1499.00'),
    'starter_cloud':   Decimal('2099.00'),
    'wordpress_pro':   Decimal('3699.00'),
    'business_cloud':  Decimal('5999.00'),
    'agency_turbo':    Decimal('8499.00'),
    'performance_max': Decimal('11999.00'),
}

PLAN_LABELS = {
    'free':            'Free — 1 website',
    'launch_lite':     'Launch Lite — 1 website · ₹1,499/year',
    'starter_cloud':   'Starter Cloud — 1 website · ₹2,099/year',
    'wordpress_pro':   'WordPress Pro — 1 website · ₹3,699/year',
    'business_cloud':  'Business Cloud — 5 websites · ₹5,999/year',
    'agency_turbo':    'Agency Turbo — 10 websites · ₹8,499/year',
    'performance_max': 'Performance Max — Unlimited websites · ₹11,999/year',
}


class Subscription(models.Model):
    class Plan(models.TextChoices):
        FREE            = 'free',            'Free'
        LAUNCH_LITE     = 'launch_lite',     'Launch Lite'
        STARTER_CLOUD   = 'starter_cloud',   'Starter Cloud'
        WORDPRESS_PRO   = 'wordpress_pro',   'WordPress Pro'
        BUSINESS_CLOUD  = 'business_cloud',  'Business Cloud'
        AGENCY_TURBO    = 'agency_turbo',    'Agency Turbo'
        PERFORMANCE_MAX = 'performance_max', 'Performance Max'

    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Active'
        PAST_DUE  = 'past_due',  'Past due'
        CANCELLED = 'cancelled', 'Cancelled'
        SUSPENDED = 'suspended', 'Suspended'

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
    trial_ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Free-plan trial expiry. Null = no trial (paid plan or legacy account).',
        db_index=True,
    )
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
        if self.trial_expired:
            return False
        return True

    @property
    def is_paid(self) -> bool:
        return self.is_active and self.plan_slug != self.Plan.FREE

    @property
    def trial_expired(self) -> bool:
        """True for free-plan accounts whose 7-day trial window has closed."""
        if self.plan_slug != self.Plan.FREE:
            return False
        if self.trial_ends_at is None:
            return False
        return self.trial_ends_at < timezone.now()

    @property
    def max_projects(self) -> int:
        if self.trial_expired:
            return 0
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
        default=Subscription.Plan.LAUNCH_LITE,
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
