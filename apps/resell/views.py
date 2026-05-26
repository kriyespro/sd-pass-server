from __future__ import annotations

import hashlib
import hmac
import json
import logging

import razorpay
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import ResellOrder, ResellProduct

logger = logging.getLogger(__name__)

CART_KEY = 'resell_cart'


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_cart(request) -> dict:
    return request.session.get(CART_KEY, {})


def _save_cart(request, cart: dict):
    request.session[CART_KEY] = cart
    request.session.modified = True


def _cart_summary(cart: dict) -> tuple[list, float]:
    """Returns (items_list, total). Fetches products from DB."""
    if not cart:
        return [], 0
    products = {str(p.pk): p for p in ResellProduct.objects.filter(pk__in=cart.keys(), is_active=True)}
    items = []
    total = 0
    for pid, qty in cart.items():
        p = products.get(pid)
        if not p:
            continue
        subtotal = float(p.price) * qty
        total += subtotal
        items.append({
            'id': p.pk,
            'name': p.name,
            'price': float(p.price),
            'qty': qty,
            'subtotal': subtotal,
            'image_url': p.image.url if p.image else '',
        })
    return items, total


# ── views ─────────────────────────────────────────────────────────────────────

def store(request):
    products = ResellProduct.objects.filter(is_active=True).order_by('-is_featured', '-created_at')
    cart = _get_cart(request)
    cart_items, cart_total = _cart_summary(cart)
    return render(request, 'pages/resell/store.jinja', {
        'products': products,
        'cart': cart,
        'cart_items': cart_items,
        'cart_total': cart_total,
        'cart_count': sum(cart.values()) if cart else 0,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })


@require_POST
def cart_add(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
        qty = max(1, int(data.get('qty', 1)))
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    product = get_object_or_404(ResellProduct, pk=pid, is_active=True)
    cart = _get_cart(request)
    cart[pid] = cart.get(pid, 0) + qty
    if product.stock > 0:
        cart[pid] = min(cart[pid], product.stock)
    _save_cart(request, cart)

    _, total = _cart_summary(cart)
    return JsonResponse({
        'ok': True,
        'cart_count': sum(cart.values()),
        'cart_total': float(total),
        'product_name': product.name,
    })


@require_POST
def cart_remove(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    cart = _get_cart(request)
    cart.pop(pid, None)
    _save_cart(request, cart)
    _, total = _cart_summary(cart)
    return JsonResponse({'ok': True, 'cart_count': sum(cart.values()), 'cart_total': float(total)})


@require_POST
def cart_update(request):
    try:
        data = json.loads(request.body)
        pid = str(int(data['product_id']))
        qty = int(data['qty'])
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Bad request'}, status=400)

    cart = _get_cart(request)
    if qty <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    _save_cart(request, cart)
    _, total = _cart_summary(cart)
    return JsonResponse({'ok': True, 'cart_count': sum(cart.values()), 'cart_total': float(total)})


@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    cart = _get_cart(request)
    if not cart:
        return JsonResponse({'error': 'Cart is empty'}, status=400)

    buyer_name = (data.get('buyer_name') or '').strip()
    buyer_email = (data.get('buyer_email') or '').strip()
    buyer_phone = (data.get('buyer_phone') or '').strip()
    if not buyer_name or not buyer_email:
        return JsonResponse({'error': 'Name and email are required'}, status=400)

    items, total = _cart_summary(cart)
    if not items:
        return JsonResponse({'error': 'No valid products in cart'}, status=400)

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

    # Persist a pending order so we can verify it later
    ResellOrder.objects.create(
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_phone=buyer_phone,
        items_snapshot=items,
        total_amount=total,
        razorpay_order_id=rz_order['id'],
        status=ResellOrder.Status.PENDING,
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

    # Clear cart after successful payment
    request.session.pop(CART_KEY, None)
    request.session.modified = True

    logger.info('Resell payment verified order=%s buyer=%s amount=%s', order_id, order.buyer_email, order.total_amount)
    return JsonResponse({'status': 'success', 'order_id': order_id})
