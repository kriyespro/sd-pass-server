from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_update_plan_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('past_due', 'Past due'),
                    ('cancelled', 'Cancelled'),
                    ('suspended', 'Suspended'),
                ],
                db_index=True,
                default='active',
                max_length=20,
            ),
        ),
    ]
