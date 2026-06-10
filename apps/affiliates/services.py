from decimal import Decimal

from django.db import models
from django.urls import reverse

from .models import (
    PARTNER_SESSION_KEY,
    PRODUCT_COMMISSION_RATE,
    REFERRAL_SESSION_KEY,
    SERVER_COMMISSION_RATE,
    Affiliate,
    AffiliateApplication,
    AffiliateCommission,
    Partner,
    PartnerCreditRedemption,
    PartnerReferral,
    generate_affiliate_code,
    get_partner_slab,
)


def get_active_affiliate(user):
    if not user or not user.is_authenticated:
        return None
    return Affiliate.objects.filter(user=user, is_active=True).first()


def get_application_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return (
        AffiliateApplication.objects.filter(user=user)
        .order_by('-created_at')
        .first()
    )


def activate_affiliate_from_application(application):
    """Create affiliate profile when admin approves an application."""
    if application.status != AffiliateApplication.Status.APPROVED:
        return None
    if not application.user_id:
        return None
    affiliate, _created = Affiliate.objects.get_or_create(
        user_id=application.user_id,
        defaults={'application': application, 'code': generate_affiliate_code()},
    )
    if affiliate.application_id != application.pk:
        affiliate.application = application
        affiliate.save(update_fields=['application'])
    if not affiliate.is_active:
        affiliate.is_active = True
        affiliate.save(update_fields=['is_active'])
    return affiliate


def capture_referral(request):
    ref = (request.GET.get('ref') or '').strip()
    if not ref:
        return
    affiliate = Affiliate.objects.filter(code__iexact=ref, is_active=True).first()
    if affiliate:
        request.session[REFERRAL_SESSION_KEY] = affiliate.code
        request.session.modified = True


def get_referral_affiliate(request):
    code = (request.session.get(REFERRAL_SESSION_KEY) or '').strip()
    if not code:
        return None
    return Affiliate.objects.filter(code__iexact=code, is_active=True).first()


def referral_query(ref_code):
    return f'?ref={ref_code}' if ref_code else ''


def build_absolute_url(request, path):
    return request.build_absolute_uri(path)


def affiliate_store_url(request, affiliate):
    path = reverse('resell:store') + referral_query(affiliate.code)
    return build_absolute_url(request, path)


def affiliate_product_url(request, affiliate, product):
    path = reverse('resell:product_detail', kwargs={'slug': product.slug}) + referral_query(affiliate.code)
    return build_absolute_url(request, path)


# ── Partner services ──────────────────────────────────────────────────────────

def get_or_create_partner(user):
    if not user or not user.is_authenticated:
        return None
    partner, _ = Partner.objects.get_or_create(
        user=user,
        defaults={'code': generate_affiliate_code()},
    )
    return partner


def partner_share_url(request, partner):
    path = reverse('billing:redeem') + f'?pref={partner.code}'
    return request.build_absolute_uri(path)


def capture_partner_referral(request):
    pref = (request.GET.get('pref') or '').strip()
    if not pref:
        return
    partner = Partner.objects.filter(code__iexact=pref, is_active=True).first()
    if partner:
        request.session[PARTNER_SESSION_KEY] = partner.code
        request.session.modified = True
        Partner.objects.filter(pk=partner.pk).update(click_count=models.F('click_count') + 1)


def get_referral_partner(request):
    code = (request.session.get(PARTNER_SESSION_KEY) or '').strip()
    if not code:
        return None
    return Partner.objects.filter(code__iexact=code, is_active=True).first()


def record_partner_referral_signup(request, new_user):
    """Call on new user signup — creates a pending PartnerReferral."""
    partner = get_referral_partner(request)
    if not partner or partner.user_id == new_user.pk:
        return
    PartnerReferral.objects.get_or_create(
        partner=partner,
        referred_user=new_user,
        defaults={'status': PartnerReferral.Status.PENDING},
    )


def credit_partner_for_plan(referred_user, plan_slug, plan_amount):
    """Call after a referred user pays for a server plan. Credits the partner."""
    from django.utils import timezone

    referral = (
        PartnerReferral.objects
        .filter(referred_user=referred_user, status=PartnerReferral.Status.PENDING)
        .select_related('partner')
        .first()
    )
    if not referral:
        return None

    partner = referral.partner
    paid_count = partner.referrals.filter(status=PartnerReferral.Status.CREDITED).count()
    rate, _label = get_partner_slab(paid_count)
    commission = (Decimal(str(plan_amount)) * rate).quantize(Decimal('0.01'))

    referral.plan_slug = plan_slug
    referral.plan_amount = Decimal(str(plan_amount))
    referral.commission_rate = rate
    referral.commission_amount = commission
    referral.status = PartnerReferral.Status.CREDITED
    referral.credited_at = timezone.now()
    referral.save()

    partner.credit_balance += commission
    partner.save(update_fields=['credit_balance'])
    return referral


def apply_partner_credit(partner, amount_to_use, plan_slug):
    """Deduct from credit_balance and record redemption. Returns amount actually deducted."""
    amount_to_use = min(Decimal(str(amount_to_use)), partner.credit_balance).quantize(Decimal('0.01'))
    if amount_to_use <= 0:
        return Decimal('0')
    partner.credit_balance -= amount_to_use
    partner.save(update_fields=['credit_balance'])
    PartnerCreditRedemption.objects.create(
        partner=partner,
        amount_redeemed=amount_to_use,
        plan_slug=plan_slug,
    )
    return amount_to_use


def record_commissions_for_order(order):
    if not order.affiliate_id or order.status != order.Status.PAID:
        return []
    if order.affiliate_commissions.exists():
        return list(order.affiliate_commissions.all())

    affiliate = order.affiliate
    if not affiliate or not affiliate.is_active:
        return []

    created = []
    for item in order.items_snapshot or []:
        item_type = item.get('type')
        if item_type == 'product':
            rate = Decimal(str(PRODUCT_COMMISSION_RATE))
        elif item_type == 'server':
            rate = Decimal(str(SERVER_COMMISSION_RATE))
        else:
            continue

        base = Decimal(str(item.get('subtotal') or 0))
        if base <= 0:
            continue

        commission_amount = (base * rate).quantize(Decimal('0.01'))
        row = AffiliateCommission.objects.create(
            affiliate=affiliate,
            order=order,
            item_type=item_type,
            item_name=item.get('name') or item_type,
            base_amount=base,
            commission_rate=rate,
            commission_amount=commission_amount,
        )
        created.append(row)
    return created
