from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uploads', '0002_alter_projectupload_file_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectupload',
            name='deploy_subfolder',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
