from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('resell', '0006_resellproduct_demo_youtube_urls'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('affiliates', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='affiliateapplication',
            name='user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='affiliate_applications',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='affiliateapplication',
            name='email',
            field=models.EmailField(max_length=254),
        ),
        migrations.CreateModel(
            name='Affiliate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=16, unique=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'application',
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='affiliate_profile',
                        to='affiliates.affiliateapplication',
                    ),
                ),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='affiliate_profile',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AffiliateCommission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'item_type',
                    models.CharField(
                        choices=[('product', 'Resell product'), ('server', 'Server plan')],
                        max_length=20,
                    ),
                ),
                ('item_name', models.CharField(max_length=200)),
                ('base_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('commission_rate', models.DecimalField(decimal_places=4, max_digits=5)),
                ('commission_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'affiliate',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='commissions',
                        to='affiliates.affiliate',
                    ),
                ),
                (
                    'order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='affiliate_commissions',
                        to='resell.resellorder',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
