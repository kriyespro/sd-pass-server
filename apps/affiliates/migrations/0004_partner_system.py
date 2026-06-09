from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('affiliates', '0003_alter_affiliateapplication_message'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=16, unique=True)),
                ('credit_balance', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='partner_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PartnerReferral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan_slug', models.CharField(blank=True, max_length=32)),
                ('plan_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('commission_rate', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=5)),
                ('commission_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('status', models.CharField(
                    choices=[('pending', 'Awaiting Purchase'), ('credited', 'Credited')],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('credited_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('partner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='referrals',
                    to='affiliates.partner',
                )),
                ('referred_user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='partner_referred_by',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at'], 'unique_together': {('partner', 'referred_user')}},
        ),
        migrations.CreateModel(
            name='PartnerCreditRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_redeemed', models.DecimalField(decimal_places=2, max_digits=10)),
                ('plan_slug', models.CharField(blank=True, max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('partner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='redemptions',
                    to='affiliates.partner',
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
