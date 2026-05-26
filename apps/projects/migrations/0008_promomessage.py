from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0007_websiteoverview'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromoMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(help_text='Message shown in the promo ticker.', max_length=220)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('order', models.PositiveSmallIntegerField(default=0, help_text='Lower = shown first.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Promo Message',
                'verbose_name_plural': 'Promo Messages',
                'ordering': ['order', 'id'],
            },
        ),
    ]
