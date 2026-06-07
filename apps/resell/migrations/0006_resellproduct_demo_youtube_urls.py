from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resell', '0005_seed_server_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='resellproduct',
            name='demo_url',
            field=models.URLField(
                blank=True,
                help_text='Live demo site URL — shown as a button on the product page.',
            ),
        ),
        migrations.AddField(
            model_name='resellproduct',
            name='youtube_url',
            field=models.URLField(
                blank=True,
                help_text='YouTube tutorial URL — shown as a button on the product page.',
            ),
        ),
    ]
