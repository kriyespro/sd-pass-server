from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def copy_legacy_images(apps, schema_editor):
    ResellProduct = apps.get_model('resell', 'ResellProduct')
    ResellProductImage = apps.get_model('resell', 'ResellProductImage')
    for product in ResellProduct.objects.exclude(image='').exclude(image__isnull=True):
        if product.image and not ResellProductImage.objects.filter(product=product).exists():
            ResellProductImage.objects.create(
                product=product,
                image=product.image,
                sort_order=0,
                alt_text=product.name,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
        ('resell', '0003_resellproduct_highlights_short_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResellServerOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('plan_slug', models.CharField(
                    blank=True,
                    choices=[
                        ('free', 'Free'),
                        ('test_plan', 'Starter Trial'),
                        ('launch_lite', 'Launch Lite'),
                        ('starter_cloud', 'Starter Cloud'),
                        ('wordpress_pro', 'WordPress Pro'),
                        ('business_cloud', 'Business Cloud'),
                        ('agency_turbo', 'Agency Turbo'),
                        ('performance_max', 'Performance Max'),
                        ('flask_addon', 'Flask Add-on'),
                    ],
                    help_text='Links to Krizn billing plan (optional).',
                    max_length=32,
                )),
                ('description', models.CharField(blank=True, max_length=300)),
                ('price', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text='Leave blank to use the billing plan price.',
                    max_digits=10,
                    null=True,
                )),
                ('checkout_url', models.URLField(
                    blank=True,
                    help_text='Optional custom checkout URL. Defaults to billing page for plan_slug.',
                )),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Resell server option',
                'verbose_name_plural': 'Resell server options',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='resellproduct',
            name='requires_server',
            field=models.BooleanField(
                default=False,
                help_text='Show supported server/hosting options on the product page.',
            ),
        ),
        migrations.CreateModel(
            name='ResellProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='resell/gallery/')),
                ('sort_order', models.PositiveSmallIntegerField(
                    default=0,
                    help_text='Lower number = shown first (featured on store cards).',
                )),
                ('alt_text', models.CharField(blank=True, max_length=200)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='images',
                    to='resell.resellproduct',
                )),
            ],
            options={
                'verbose_name': 'Product image',
                'verbose_name_plural': 'Product images',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.AddField(
            model_name='resellproduct',
            name='supported_servers',
            field=models.ManyToManyField(
                blank=True,
                help_text='Server plans customers can buy to deploy this product.',
                related_name='products',
                to='resell.resellserveroption',
            ),
        ),
        migrations.RunPython(copy_legacy_images, migrations.RunPython.noop),
    ]
