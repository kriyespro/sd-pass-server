from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import ResellOrder, ResellProduct, ResellProductImage, ResellServerOption
from .services import DEPLOYMENT_PLAN_SLUGS, ensure_server_options


class ResellServerOptionAdminForm(forms.ModelForm):
    class Meta:
        model = ResellServerOption
        fields = '__all__'
        labels = {
            'plan_slug': 'Subscription plan',
        }
        widgets = {
            'plan_slug': forms.Select(attrs={'style': 'min-width: 360px;'}),
        }


class ResellProductAdminForm(forms.ModelForm):
    subscription_plans = forms.ModelMultipleChoiceField(
        label='Supported subscription plans (server)',
        queryset=ResellServerOption.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Check the hosting plans available for this product.',
    )

    class Meta:
        model = ResellProduct
        exclude = ('supported_servers',)

    def __init__(self, *args, **kwargs):
        ensure_server_options()
        super().__init__(*args, **kwargs)
        queryset = ResellServerOption.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['subscription_plans'].queryset = queryset
        self.fields['subscription_plans'].label_from_instance = self._plan_label
        if self.instance.pk:
            self.initial['subscription_plans'] = list(
                self.instance.supported_servers.values_list('pk', flat=True)
            )

    @staticmethod
    def _plan_label(option):
        price = option.display_price
        label = f'{option.name} — ₹{int(price)}' if price is not None else option.name
        return f'{label} · {option.specs_line}'

    def _apply_subscription_plans(self, obj):
        selected = list(getattr(self, '_selected_plans', None) or [])
        if not obj.requires_server:
            obj.supported_servers.clear()
            return
        if not selected:
            selected = list(
                ResellServerOption.objects.filter(
                    plan_slug__in=DEPLOYMENT_PLAN_SLUGS,
                    is_active=True,
                ).order_by('sort_order', 'name')
            )
        obj.supported_servers.set(selected)

    def save(self, commit=True):
        obj = super().save(commit)
        self._selected_plans = list(self.cleaned_data.get('subscription_plans') or [])
        if commit:
            self._apply_subscription_plans(obj)
        return obj

    def save_m2m(self):
        self._apply_subscription_plans(self.instance)


class ResellProductImageInline(admin.TabularInline):
    model = ResellProductImage
    extra = 1
    fields = ('image', 'sort_order', 'alt_text', 'thumb')
    readonly_fields = ('thumb',)
    ordering = ('sort_order', 'pk')

    @admin.display(description='Preview')
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:36px;width:36px;object-fit:cover;border-radius:4px;">',
                obj.image.url,
            )
        return '—'


@admin.register(ResellServerOption)
class ResellServerOptionAdmin(admin.ModelAdmin):
    form = ResellServerOptionAdminForm
    list_display = ('name', 'plan_slug', 'price_display', 'sort_order', 'is_active')
    list_editable = ('sort_order', 'is_active')
    list_filter = ('is_active', 'plan_slug')
    search_fields = ('name', 'description', 'plan_slug')
    ordering = ('sort_order', 'name')
    fieldsets = (
        (None, {
            'fields': ('name', 'plan_slug', 'description', 'price', 'checkout_url'),
        }),
        ('Display', {
            'fields': ('sort_order', 'is_active'),
        }),
    )

    @admin.display(description='Price')
    def price_display(self, obj):
        price = obj.display_price
        return f'₹{price}' if price is not None else '—'


@admin.register(ResellProduct)
class ResellProductAdmin(admin.ModelAdmin):
    form = ResellProductAdminForm
    list_display = ('thumb', 'name', 'category', 'price', 'original_price', 'stock_display', 'requires_server', 'is_featured', 'is_active', 'created_at')
    list_display_links = ('thumb', 'name')
    list_editable = ('is_featured', 'is_active')
    list_filter = ('category', 'is_active', 'is_featured', 'requires_server')
    search_fields = ('name', 'slug', 'description', 'short_description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at', 'preview_image')
    inlines = [ResellProductImageInline]
    ordering = ('-is_featured', '-created_at')
    fieldsets = (
        ('Product', {
            'fields': ('name', 'slug', 'category', 'badge_text'),
        }),
        ('Pricing', {
            'fields': ('price', 'original_price'),
        }),
        ('Demo & tutorial', {
            'fields': ('demo_url', 'youtube_url'),
            'description': 'Optional links shown on the product page — live demo site and YouTube tutorial.',
        }),
        ('Legacy image', {
            'fields': ('image', 'preview_image'),
            'classes': ('collapse',),
            'description': 'Use “Product images” below. First image = featured. Legacy field kept for old data only.',
        }),
        ('Deployment / server', {
            'fields': ('requires_server', 'subscription_plans'),
            'description': 'Enable “Requires server” and pick subscription plans buyers can purchase to host this product.',
        }),
        ('Inventory', {
            'fields': ('stock', 'is_active', 'is_featured'),
        }),
        ('Description', {
            'fields': ('short_description', 'description', 'highlights'),
            'description': (
                'Short description = store card teaser. '
                'Description = full detail page text. '
                'Highlights = one bullet per line.'
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if hasattr(form, '_selected_plans'):
            form._apply_subscription_plans(form.instance)

    @admin.display(description='')
    def thumb(self, obj):
        url = obj.featured_image_url
        if url:
            return format_html('<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:6px;">', url)
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
        url = obj.featured_image_url
        if url:
            return format_html('<img src="{}" style="max-height:180px;border-radius:8px;">', url)
        return '—'


@admin.register(ResellOrder)
class ResellOrderAdmin(admin.ModelAdmin):
    list_display = ('razorpay_order_id', 'buyer_name', 'buyer_email', 'affiliate', 'total_amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('buyer_name', 'buyer_email', 'razorpay_order_id', 'razorpay_payment_id')
    readonly_fields = ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature', 'items_snapshot', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        ('Buyer', {'fields': ('buyer_name', 'buyer_email', 'buyer_phone')}),
        ('Order', {'fields': ('total_amount', 'status', 'affiliate', 'items_snapshot')}),
        ('Razorpay', {'fields': ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
