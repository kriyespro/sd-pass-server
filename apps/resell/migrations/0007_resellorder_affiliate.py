from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('affiliates', '0002_affiliate_program'),
        ('resell', '0006_resellproduct_demo_youtube_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='resellorder',
            name='affiliate',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='resell_orders',
                to='affiliates.affiliate',
            ),
        ),
    ]
