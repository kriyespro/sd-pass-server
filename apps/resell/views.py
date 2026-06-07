from __future__ import annotations

import hashlib
import hmac
import json
import logging

import razorpay
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import ResellOrder, ResellProduct, ResellServerOption
from .services import (
    cart_count,
    cart_summary,
    clear_cart_state,
    fulfill_order_server_plans,
    get_cart_state,
    product_server_options,
    save_cart_state,
    server_options_payload,
    _allowed_server_for_product,
)
from apps.affiliates.services import get_referral_affiliate, record_commissions_for_order

logger = logging.getLogger(__name__)

User = get_user_model()

PRODUCT_QUERYSET = ResellProduct.objects.prefetch_related(
    'images',
    'supported_servers',
)


def _cart_context(request):
    state = get_cart_state(request)
    items, total = cart_summary(state, product_queryset=PRODUCT_QUERYSET)
    return {
        'cart_items': items,
        'cart_total': total,
        'cart_count': cart_count(state),
    }


def store(request):
    products = PRODUCT_QUERYSET.filter(is_active=True).order_by('-is_featured', '-created_at')
    ctx = _cart_context(request)
    ctx.update({
        'products': products,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })
    return render(request, 'pages/resell/store.jinja', ctx)


def product_detail(request, slug):
    product = get_object_or_404(PRODUCT_QUERYSET, slug=slug, is_active=True)
    server_options = product_server_options(product)
    related = (
        PRODUCT_QUERYSET.filter(is_active=True)
        .exclude(pk=product.pk)
        .order_by('-is_featured', '-created_at')[:3]
    )
    ctx = _cart_context(request)
    ctx.update({
        'product': product,
        'server_options': server_options,
        'server_options_json': server_options_payload(server_options),
        'related_products': related,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })
    return render(request, 'pages/resell/product_detail.jinja', ctx)


@require_POST
def cart_add(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
        qty = max(1, int(data.get('qty', 1)))
        server_option_id = data.get('server_option_id')
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    product = get_object_or_404(ResellProduct, pk=pid, is_active=True)
    state = get_cart_state(request)

    if product.requires_server:
        if not server_option_id:
            return JsonResponse({'error': 'Select a hosting plan first'}, status=400)
        if not _allowed_server_for_product(product, server_option_id):
            return JsonResponse({'error': 'Invalid hosting plan for this product'}, status=400)
        state['servers'][pid] = str(int(server_option_id))
    else:
        state['servers'].pop(pid, None)

    state['products'][pid] = state['products'].get(pid, 0) + qty
    if product.stock > 0:
        state['products'][pid] = min(state['products'][pid], product.stock)

    save_cart_state(request, state)
    items, total = cart_summary(state, product_queryset=PRODUCT_QUERYSET)
    return JsonResponse({
        'ok': True,
        'cart_count': cart_count(state),
        'cart_total': float(total),
        'cart_items': items,
        'product_name': product.name,
    })


@require_POST
def cart_remove(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    state = get_cart_state(request)
    state['products'].pop(pid, None)
    state['servers'].pop(pid, None)
    save_cart_state(request, state)
    items, total = cart_summary(state, product_queryset=PRODUCT_QUERYSET)
    return JsonResponse({
        'ok': True,
        'cart_count': cart_count(state),
        'cart_total': float(total),
        'cart_items': items,
    })


@require_POST
def cart_update(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
        qty = int(data['qty'])
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    state = get_cart_state(request)
    if qty <= 0:
        state['products'].pop(pid, None)
        state['servers'].pop(pid, None)
    else:
        state['products'][pid] = qty
    save_cart_state(request, state)
    items, total = cart_summary(state, product_queryset=PRODUCT_QUERYSET)
    return JsonResponse({
        'ok': True,
        'cart_count': cart_count(state),
        'cart_total': float(total),
        'cart_items': items,
    })


@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    state = get_cart_state(request)
    if not state['products']:
        return JsonResponse({'error': 'Cart is empty'}, status=400)

    buyer_name = (data.get('buyer_name') or '').strip()
    buyer_email = (data.get('buyer_email') or '').strip()
    buyer_phone = (data.get('buyer_phone') or '').strip()
    if not buyer_name or not buyer_email:
        return JsonResponse({'error': 'Name and email are required'}, status=400)

    items, total = cart_summary(state, product_queryset=PRODUCT_QUERYSET)
    if not items:
        return JsonResponse({'error': 'No valid products in cart'}, status=400)

    for product in PRODUCT_QUERYSET.filter(pk__in=state['products'].keys(), requires_server=True):
        if str(product.pk) not in state['servers']:
            return JsonResponse(
                {'error': f'Select a hosting plan for "{product.name}"'},
                status=400,
            )

    amount_paise = int(total * 100)
    if amount_paise < 100:
        return JsonResponse({'error': 'Order total too small'}, status=400)

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        rz_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'resell_{buyer_email[:20]}',
        })
    except Exception as exc:
        logger.exception('Razorpay create_order (resell) failed: %s', exc)
        return JsonResponse({'error': 'Payment service error. Please try again.'}, status=500)

    ResellOrder.objects.create(
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_phone=buyer_phone,
        items_snapshot=items,
        total_amount=total,
        razorpay_order_id=rz_order['id'],
        status=ResellOrder.Status.PENDING,
        affiliate=get_referral_affiliate(request),
    )

    return JsonResponse({
        'order_id': rz_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
    })


@require_POST
def verify_payment(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    payment_id = data.get('razorpay_payment_id', '')
    order_id = data.get('razorpay_order_id', '')
    signature = data.get('razorpay_signature', '')

    if not all([payment_id, order_id, signature]):
        return JsonResponse({'error': 'Missing payment fields'}, status=400)

    msg = f'{order_id}|{payment_id}'.encode()
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning('Razorpay resell signature mismatch order=%s', order_id)
        return JsonResponse({'error': 'Payment verification failed'}, status=400)

    order = ResellOrder.objects.filter(razorpay_order_id=order_id).first()
    if not order:
        return JsonResponse({'error': 'Order not found'}, status=404)

    order.razorpay_payment_id = payment_id
    order.razorpay_signature = signature
    order.status = ResellOrder.Status.PAID
    order.save(update_fields=['razorpay_payment_id', 'razorpay_signature', 'status', 'updated_at'])

    user = request.user if request.user.is_authenticated else None
    if not user:
        user = User.objects.filter(email__iexact=order.buyer_email).first()
    fulfill_order_server_plans(order, user)
    record_commissions_for_order(order)

    clear_cart_state(request)

    logger.info('Resell payment verified order=%s buyer=%s amount=%s', order_id, order.buyer_email, order.total_amount)
    return JsonResponse({'status': 'success', 'order_id': order_id})
