from django.db import migrations, models


NEW_CHOICES = [
    ('free',            'Free'),
    ('launch_lite',     'Launch Lite'),
    ('starter_cloud',   'Starter Cloud'),
    ('wordpress_pro',   'WordPress Pro'),
    ('business_cloud',  'Business Cloud'),
    ('agency_turbo',    'Agency Turbo'),
    ('performance_max', 'Performance Max'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_subscription_trial_ends_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='plan_slug',
            field=models.CharField(
                choices=NEW_CHOICES,
                db_index=True,
                default='free',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='couponcode',
            name='plan',
            field=models.CharField(
                choices=NEW_CHOICES,
                default='launch_lite',
                max_length=32,
            ),
        ),
    ]
