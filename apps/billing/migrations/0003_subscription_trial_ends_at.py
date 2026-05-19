from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_coupon_code_and_plans'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='trial_ends_at',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text='Free-plan trial expiry. Null = no trial (paid plan or legacy account).',
                null=True,
            ),
        ),
    ]
