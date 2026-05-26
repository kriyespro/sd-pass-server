from decimal import Decimal

from django.db import models


class ResellProduct(models.Model):
    class Category(models.TextChoices):
        DIGITAL = 'digital', 'Digital'
        PHYSICAL = 'physical', 'Physical'
        COURSE = 'course', 'Course'
        SERVICE = 'service', 'Service'
        OTHER = 'other', 'Other'

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
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


class ResellOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'

    buyer_name = models.CharField(max_length=120)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=20, blank=True)
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
