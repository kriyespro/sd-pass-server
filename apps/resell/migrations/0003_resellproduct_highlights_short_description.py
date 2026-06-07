from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resell', '0002_alter_resellorder_items_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='resellproduct',
            name='highlights',
            field=models.TextField(
                blank=True,
                help_text='Optional bullet points — one feature per line (shown on product page).',
            ),
        ),
        migrations.AddField(
            model_name='resellproduct',
            name='short_description',
            field=models.CharField(
                blank=True,
                help_text='Short line for store cards (optional). Falls back to full description.',
                max_length=300,
            ),
        ),
        migrations.AlterField(
            model_name='resellproduct',
            name='description',
            field=models.TextField(
                blank=True,
                help_text='Full product details shown on the product page.',
            ),
        ),
    ]
