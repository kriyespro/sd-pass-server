import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models


PRODUCT_COMMISSION_RATE = 0.20
SERVER_COMMISSION_RATE = 0.10
REFERRAL_SESSION_KEY = 'affiliate_ref'
PARTNER_SESSION_KEY = 'partner_ref'

# (min_paid_referrals, rate, tier_label)
PARTNER_SLABS = [
    (10, Decimal('0.20'), 'Gold'),
    (5,  Decimal('0.15'), 'Silver'),
    (0,  Decimal('0.10'), 'Bronze'),
]


def generate_affiliate_code():
    return secrets.token_urlsafe(6).replace('-', '').upper()[:8]


def get_partner_slab(paid_referral_count):
    for min_count, rate, label in PARTNER_SLABS:
        if paid_referral_count >= min_count:
            return rate, label
    return Decimal('0.10'), 'Bronze'


class AffiliateApplication(models.Model):
    class Platform(models.TextChoices):
        YOUTUBE = 'youtube', 'YouTube'
        INSTAGRAM = 'instagram', 'Instagram'
        TWITTER = 'twitter', 'Twitter / X'
        LINKEDIN = 'linkedin', 'LinkedIn'
        BLOG = 'blog', 'Blog / Website'
        TIKTOK = 'tiktok', 'TikTok'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='affiliate_applications',
    )
    name = models.CharField(max_length=120)
    email = models.EmailField()
    website = models.URLField(blank=True, help_text='Your main website or channel URL.')
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.OTHER)
    audience_size = models.CharField(
        max_length=30,
        blank=True,
        help_text='Approximate followers/subscribers (e.g. 5000, 10k).',
    )
    message = models.TextField(
        max_length=1000,
        help_text='Why do you want to become an affiliate? How will you promote Krizn?',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    admin_notes = models.TextField(blank=True, help_text='Internal notes (not shown to applicant).')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Affiliate Application'
        verbose_name_plural = 'Affiliate Applications'

    def __str__(self):
        return f'{self.name} <{self.email}> [{self.status}]'


class Affiliate(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='affiliate_profile',
    )
    application = models.OneToOneField(
        AffiliateApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='affiliate_profile',
    )
    code = models.CharField(max_length=16, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} · {self.code}'

    @property
    def total_earnings(self):
        return (
            self.commissions.aggregate(total=models.Sum('commission_amount'))['total']
            or 0
        )


class AffiliateCommission(models.Model):
    class ItemType(models.TextChoices):
        PRODUCT = 'product', 'Resell product'
        SERVER = 'server', 'Server plan'

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name='commissions')
    order = models.ForeignKey(
        'resell.ResellOrder',
        on_delete=models.CASCADE,
        related_name='affiliate_commissions',
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    item_name = models.CharField(max_length=200)
    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.affiliate.code} · ₹{self.commission_amount} ({self.item_type})'


# ── Partner system (auto-created for every user, no application needed) ──────

class Partner(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='partner_profile',
    )
    code = models.CharField(max_length=16, unique=True, db_index=True)
    credit_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    click_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} · partner · {self.code}'

    @property
    def paid_referral_count(self):
        return self.referrals.filter(status=PartnerReferral.Status.CREDITED).count()

    @property
    def slab_info(self):
        count = self.paid_referral_count
        rate, label = get_partner_slab(count)
        next_slab = None
        for min_count, next_rate, next_label in PARTNER_SLABS:
            if min_count > count:
                next_slab = {'at': min_count, 'rate': int(next_rate * 100), 'label': next_label, 'need': min_count - count}
                break
        return {
            'rate': rate,
            'rate_pct': int(rate * 100),
            'label': label,
            'count': count,
            'next': next_slab,
        }

    @property
    def total_earned(self):
        return (
            self.referrals.filter(status=PartnerReferral.Status.CREDITED)
            .aggregate(total=models.Sum('commission_amount'))['total']
            or Decimal('0')
        )

    @property
    def total_redeemed(self):
        return (
            self.redemptions.aggregate(total=models.Sum('amount_redeemed'))['total']
            or Decimal('0')
        )


class PartnerReferral(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting Purchase'
        CREDITED = 'credited', 'Credited'

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='referrals')
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_referred_by',
    )
    plan_slug = models.CharField(max_length=32, blank=True)
    plan_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0'))
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    credited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('partner', 'referred_user')]

    def __str__(self):
        return f'{self.partner.code} → {self.referred_user_id} [{self.status}]'


class PartnerCreditRedemption(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='redemptions')
    amount_redeemed = models.DecimalField(max_digits=10, decimal_places=2)
    plan_slug = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.partner.code} redeemed ₹{self.amount_redeemed} on {self.plan_slug}'
