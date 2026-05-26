from django.contrib import admin
from django.utils.html import format_html

from .models import ResellOrder, ResellProduct


@admin.register(ResellProduct)
class ResellProductAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'name', 'category', 'price', 'original_price', 'stock_display', 'is_featured', 'is_active', 'created_at')
    list_display_links = ('thumb', 'name')
    list_editable = ('is_featured', 'is_active')
    list_filter = ('category', 'is_active', 'is_featured')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at', 'preview_image')
    ordering = ('-is_featured', '-created_at')
    fieldsets = (
        ('Product', {
            'fields': ('name', 'slug', 'category', 'badge_text'),
        }),
        ('Pricing', {
            'fields': ('price', 'original_price'),
        }),
        ('Image', {
            'fields': ('image', 'preview_image'),
        }),
        ('Inventory', {
            'fields': ('stock', 'is_active', 'is_featured'),
        }),
        ('Description', {
            'fields': ('description',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='')
    def thumb(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:6px;">', obj.image.url)
        return '—'

    @admin.display(description='Stock')
    def stock_display(self, obj):
        if obj.stock == 0:
            return format_html('<span style="color:#6ee7b7;">∞ Unlimited</span>')
        if obj.stock <= 5:
            return format_html('<span style="color:#fca5a5;">{} left</span>', obj.stock)
        return obj.stock

    @admin.display(description='Image preview')
    def preview_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:180px;border-radius:8px;">', obj.image.url)
        return '—'


@admin.register(ResellOrder)
class ResellOrderAdmin(admin.ModelAdmin):
    list_display = ('razorpay_order_id', 'buyer_name', 'buyer_email', 'total_amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('buyer_name', 'buyer_email', 'razorpay_order_id', 'razorpay_payment_id')
    readonly_fields = ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature', 'items_snapshot', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        ('Buyer', {'fields': ('buyer_name', 'buyer_email', 'buyer_phone')}),
        ('Order', {'fields': ('total_amount', 'status', 'items_snapshot')}),
        ('Razorpay', {'fields': ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
