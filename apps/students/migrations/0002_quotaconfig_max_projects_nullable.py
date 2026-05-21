from django.db import migrations, models


def clear_default_max_projects(apps, schema_editor):
    """
    The old default (3) was auto-applied to every user via signal.
    Rows still at 3 are effectively "not set" — reset them to NULL so billing
    plan becomes the source of truth for those users.
    """
    QuotaConfig = apps.get_model('students', 'QuotaConfig')
    QuotaConfig.objects.filter(max_projects=3).update(max_projects=None)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotaconfig',
            name='max_projects',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                default=None,
                help_text='Trainer override. Leave blank to use the billing plan limit.',
            ),
        ),
        migrations.RunPython(clear_default_max_projects, migrations.RunPython.noop),
    ]
