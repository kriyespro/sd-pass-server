from django.db import migrations, models


def backfill_verified_custom_hosts(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    Project.objects.filter(custom_hostname__isnull=False).exclude(custom_hostname='').update(
        custom_hostname_verified=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_custom_hostname'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='custom_hostname_verified',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='True after DNS TXT challenge proves domain ownership.',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='custom_domain_challenge_token',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Secret token the student publishes in a TXT record before routing goes live.',
                max_length=64,
            ),
        ),
        migrations.RunPython(backfill_verified_custom_hosts, migrations.RunPython.noop),
    ]
