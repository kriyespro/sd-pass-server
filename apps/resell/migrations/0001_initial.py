from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ResellProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(max_length=200, unique=True)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('original_price', models.DecimalField(blank=True, decimal_places=2, help_text='Strike-through price (leave blank to hide discount badge).', max_digits=10, null=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='resell/')),
                ('category', models.CharField(choices=[('digital', 'Digital'), ('physical', 'Physical'), ('course', 'Course'), ('service', 'Service'), ('other', 'Other')], default='other', max_length=20)),
                ('stock', models.PositiveIntegerField(default=0, help_text='0 = unlimited stock.')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('is_featured', models.BooleanField(db_index=True, default=False)),
                ('badge_text', models.CharField(blank=True, help_text='Short badge label (e.g. "Best Seller", "New"). Leave blank to hide.', max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Resell Product', 'verbose_name_plural': 'Resell Products', 'ordering': ['-is_featured', '-created_at']},
        ),
        migrations.CreateModel(
            name='ResellOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('buyer_name', models.CharField(max_length=120)),
                ('buyer_email', models.EmailField()),
                ('buyer_phone', models.CharField(blank=True, max_length=20)),
                ('items_snapshot', models.JSONField()),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('razorpay_order_id', models.CharField(db_index=True, max_length=60, unique=True)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=60)),
                ('razorpay_signature', models.CharField(blank=True, max_length=128)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Resell Order', 'verbose_name_plural': 'Resell Orders', 'ordering': ['-created_at']},
        ),
    ]
