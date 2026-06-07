from apps.billing.models import PLAN_LABELS, PLAN_PRICES, Subscription

from .models import ResellProduct, ResellServerOption

DEPLOYMENT_PLAN_SLUGS = [
    slug for slug, _ in Subscription.Plan.choices if slug != Subscription.Plan.FREE
]

CART_SESSION_KEY = 'resell_cart'


def deployment_plan_choices():
    return [(slug, PLAN_LABELS.get(slug, slug)) for slug in DEPLOYMENT_PLAN_SLUGS]


def ensure_server_options():
    """Create/update ResellServerOption rows for each billing subscription plan."""
    for idx, slug in enumerate(DEPLOYMENT_PLAN_SLUGS):
        label = PLAN_LABELS.get(slug, slug)
        name = label.split('—')[0].strip() if '—' in label else label
        ResellServerOption.objects.update_or_create(
            plan_slug=slug,
            defaults={
                'name': name,
                'description': label,
                'price': PLAN_PRICES.get(slug),
                'sort_order': idx,
                'is_active': True,
            },
        )


def product_server_options(product):
    """Plans to show on product page when deployment/hosting is required."""
    if not product.requires_server:
        return []
    ensure_server_options()
    linked = product.supported_servers.filter(is_active=True).order_by('sort_order', 'name')
    if linked.exists():
        return list(linked)
    return list(ResellServerOption.objects.filter(is_active=True).order_by('sort_order', 'name'))


def server_options_payload(options):
    return [
        {
            'id': option.pk,
            'name': option.name,
            'price': float(option.display_price or 0),
            'description': option.description,
            'plan_slug': option.plan_slug,
            'period': option.hosting_specs['period'],
            'ram': option.hosting_specs['ram'],
            'cpu': option.hosting_specs['cpu'],
            'storage': option.hosting_specs['storage'],
            'specs_line': option.specs_line,
        }
        for option in options
    ]


def normalize_cart(raw):
    if not raw:
        return {'products': {}, 'servers': {}}
    if isinstance(raw, dict) and 'products' in raw:
        return {
            'products': {str(k): int(v) for k, v in raw.get('products', {}).items()},
            'servers': {str(k): str(v) for k, v in raw.get('servers', {}).items()},
        }
    return {
        'products': {str(k): int(v) for k, v in raw.items()},
        'servers': {},
    }


def get_cart_state(request):
    return normalize_cart(request.session.get(CART_SESSION_KEY))


def save_cart_state(request, state):
    request.session[CART_SESSION_KEY] = normalize_cart(state)
    request.session.modified = True


def clear_cart_state(request):
    request.session.pop(CART_SESSION_KEY, None)
    request.session.modified = True


def _allowed_server_for_product(product, server_option_id):
    allowed_ids = {option.pk for option in product_server_options(product)}
    return int(server_option_id) in allowed_ids


def cart_summary(state, *, product_queryset=None):
    state = normalize_cart(state)
    if not state['products']:
        return [], 0

    queryset = product_queryset or ResellProduct.objects.filter(is_active=True).prefetch_related('images')
    products = {str(p.pk): p for p in queryset.filter(pk__in=state['products'].keys())}
    server_ids = [int(sid) for sid in state['servers'].values() if str(sid).isdigit()]
    servers = {
        str(s.pk): s
        for s in ResellServerOption.objects.filter(pk__in=server_ids, is_active=True)
    }

    items = []
    total = 0.0
    for pid, qty in state['products'].items():
        product = products.get(pid)
        if not product:
            continue
        product_subtotal = float(product.price) * qty
        total += product_subtotal
        items.append({
            'type': 'product',
            'id': product.pk,
            'product_id': product.pk,
            'name': product.name,
            'price': float(product.price),
            'qty': qty,
            'subtotal': product_subtotal,
            'image_url': product.featured_image_url,
        })

        server_id = state['servers'].get(pid)
        server = servers.get(str(server_id)) if server_id else None
        if server:
            server_price = float(server.display_price or 0)
            server_subtotal = server_price * qty
            total += server_subtotal
            items.append({
                'type': 'server',
                'id': f'server-{server.pk}',
                'product_id': product.pk,
                'server_option_id': server.pk,
                'plan_slug': server.plan_slug,
                'name': f'{server.name} hosting',
                'price': server_price,
                'qty': qty,
                'subtotal': server_subtotal,
                'image_url': '',
            })

    return items, total


def cart_count(state):
    return sum(normalize_cart(state)['products'].values())


def fulfill_order_server_plans(order, user):
    """Activate subscription plan(s) included in a paid resell order."""
    if user is None:
        return

    from datetime import timedelta

    from django.utils import timezone

    from apps.billing.models import Subscription
    from apps.billing.services import get_or_create_subscription

    plan_slug = None
    for item in order.items_snapshot:
        if item.get('type') == 'server' and item.get('plan_slug'):
            plan_slug = item['plan_slug']
            break

    if not plan_slug or plan_slug not in DEPLOYMENT_PLAN_SLUGS:
        return

    plan_days = 30 if plan_slug == 'test_plan' else 365
    sub = get_or_create_subscription(user)
    sub.plan_slug = plan_slug
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = timezone.now() + timedelta(days=plan_days)
    sub.trial_ends_at = None
    sub.save(update_fields=['plan_slug', 'status', 'current_period_end', 'trial_ends_at', 'updated_at'])
