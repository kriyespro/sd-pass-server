from decimal import Decimal

from django.urls import reverse

from .models import (
    PRODUCT_COMMISSION_RATE,
    REFERRAL_SESSION_KEY,
    SERVER_COMMISSION_RATE,
    Affiliate,
    AffiliateApplication,
    AffiliateCommission,
    generate_affiliate_code,
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
