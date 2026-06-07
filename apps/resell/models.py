from decimal import Decimal

from django.db import models
from django.urls import reverse

from apps.billing.models import PLAN_PRICES, Subscription, plan_hosting_specs


class ResellServerOption(models.Model):
    """Hosting/server plan that can be linked to products needing deployment."""

    name = models.CharField(max_length=120)
    plan_slug = models.CharField(
        max_length=32,
        choices=Subscription.Plan.choices,
        blank=True,
        help_text='Links to Krizn billing plan (optional).',
    )
    description = models.CharField(max_length=300, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Leave blank to use the billing plan price.',
    )
    checkout_url = models.URLField(
        blank=True,
        help_text='Optional custom checkout URL. Defaults to billing page for plan_slug.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Resell server option'
        verbose_name_plural = 'Resell server options'

    def __str__(self):
        if self.plan_slug:
            return f'{self.name} ({self.get_plan_slug_display()})'
        return self.name

    @property
    def display_price(self):
        if self.price is not None:
            return self.price
        if self.plan_slug:
            return PLAN_PRICES.get(self.plan_slug)
        return None

    def get_checkout_url(self):
        if self.checkout_url:
            return self.checkout_url
        if self.plan_slug:
            return f'{reverse("billing:redeem")}?plan={self.plan_slug}'
        return reverse('billing:redeem')

    @property
    def hosting_specs(self):
        if self.plan_slug:
            return plan_hosting_specs(self.plan_slug)
        return {
            'period': '1 year',
            'ram': '—',
            'cpu': '—',
            'storage': '—',
        }

    @property
    def specs_line(self):
        specs = self.hosting_specs
        return f"{specs['period']} · {specs['ram']} RAM · {specs['cpu']} · {specs['storage']}"


class ResellProduct(models.Model):
    class Category(models.TextChoices):
        DIGITAL = 'digital', 'Digital'
        PHYSICAL = 'physical', 'Physical'
        COURSE = 'course', 'Course'
        SERVICE = 'service', 'Service'
        OTHER = 'other', 'Other'

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    short_description = models.CharField(
        max_length=300,
        blank=True,
        help_text='Short line for store cards (optional). Falls back to full description.',
    )
    description = models.TextField(
        blank=True,
        help_text='Full product details shown on the product page.',
    )
    highlights = models.TextField(
        blank=True,
        help_text='Optional bullet points — one feature per line (shown on product page).',
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Strike-through price (leave blank to hide discount badge).',
    )
    image = models.ImageField(upload_to='resell/', blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    stock = models.PositiveIntegerField(
        default=0,
        help_text='0 = unlimited stock.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    badge_text = models.CharField(
        max_length=30, blank=True,
        help_text='Short badge label (e.g. "Best Seller", "New"). Leave blank to hide.',
    )
    requires_server = models.BooleanField(
        default=False,
        help_text='Show supported server/hosting options on the product page.',
    )
    supported_servers = models.ManyToManyField(
        ResellServerOption,
        blank=True,
        related_name='products',
        help_text='Server plans customers can buy to deploy this product.',
    )
    demo_url = models.URLField(
        blank=True,
        help_text='Live demo site URL — shown as a button on the product page.',
    )
    youtube_url = models.URLField(
        blank=True,
        help_text='YouTube tutorial URL — shown as a button on the product page.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']
        verbose_name = 'Resell Product'
        verbose_name_plural = 'Resell Products'

    def __str__(self):
        return self.name

    @property
    def in_stock(self):
        return self.stock == 0 or self.stock > 0

    @property
    def discount_pct(self):
        if self.original_price and self.original_price > self.price:
            return int(100 - (self.price / self.original_price * 100))
        return 0

    def price_paise(self):
        return int(self.price * 100)

    @property
    def highlight_lines(self):
        return [line.strip() for line in self.highlights.splitlines() if line.strip()]

    @property
    def card_summary(self):
        if self.short_description.strip():
            return self.short_description.strip()
        if self.description.strip():
            text = self.description.strip().replace('\n', ' ')
            return text[:160] + ('…' if len(text) > 160 else '')
        return ''

    @property
    def stock_label(self):
        return 'Available' if self.stock == 0 else f'{self.stock} left'

    @property
    def featured_image(self):
        first = self.images.order_by('sort_order', 'pk').first()
        if first:
            return first.image
        return self.image

    @property
    def featured_image_url(self):
        img = self.featured_image
        return img.url if img else ''

    @property
    def gallery(self):
        images = list(self.images.all())
        if images:
            return images
        if self.image:
            return [ResellProductImage(image=self.image, alt_text=self.name)]
        return []


class ResellProductImage(models.Model):
    product = models.ForeignKey(
        ResellProduct,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='resell/gallery/')
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text='Lower number = shown first (featured on store cards).',
    )
    alt_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Product image'
        verbose_name_plural = 'Product images'

    def __str__(self):
        return f'{self.product.name} #{self.pk}'

    @property
    def alt(self):
        return self.alt_text.strip() or self.product.name


class ResellOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'

    buyer_name = models.CharField(max_length=120)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=20, blank=True)
    affiliate = models.ForeignKey(
        'affiliates.Affiliate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resell_orders',
    )
    items_snapshot = models.JSONField(
        help_text='Cart items at time of purchase: [{product_id, name, qty, unit_price}]',
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    razorpay_order_id = models.CharField(max_length=60, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=60, blank=True)
    razorpay_signature = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Resell Order'
        verbose_name_plural = 'Resell Orders'

    def __str__(self):
        return f'Order {self.razorpay_order_id} — {self.buyer_email} [{self.status}]'
