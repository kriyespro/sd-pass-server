from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_ops', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetoptimizationrun',
            name='sites_scanned',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Static sites with any files on disk',
            ),
        ),
        migrations.AlterField(
            model_name='assetoptimizationrun',
            name='projects_processed',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Sites that contained CSS, JS, or images',
            ),
        ),
    ]
