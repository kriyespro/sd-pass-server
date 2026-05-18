from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_add_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='site_subfolder',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Most-recently deployed subfolder path (e.g. "myweb"). Empty = site root.',
                max_length=64,
            ),
        ),
    ]
