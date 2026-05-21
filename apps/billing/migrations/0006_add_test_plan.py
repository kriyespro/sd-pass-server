from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_subscription_status_suspended'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='plan_slug',
            field=models.CharField(
                choices=[
                    ('free', 'Free'),
                    ('test_plan', 'Test Plan'),
                    ('launch_lite', 'Launch Lite'),
                    ('starter_cloud', 'Starter Cloud'),
                    ('wordpress_pro', 'WordPress Pro'),
                    ('business_cloud', 'Business Cloud'),
                    ('agency_turbo', 'Agency Turbo'),
                    ('performance_max', 'Performance Max'),
                ],
                db_index=True,
                default='free',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='couponcode',
            name='plan',
            field=models.CharField(
                choices=[
                    ('free', 'Free'),
                    ('test_plan', 'Test Plan'),
                    ('launch_lite', 'Launch Lite'),
                    ('starter_cloud', 'Starter Cloud'),
                    ('wordpress_pro', 'WordPress Pro'),
                    ('business_cloud', 'Business Cloud'),
                    ('agency_turbo', 'Agency Turbo'),
                    ('performance_max', 'Performance Max'),
                ],
                default='launch_lite',
                max_length=32,
            ),
        ),
    ]
