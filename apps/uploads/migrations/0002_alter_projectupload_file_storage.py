# Align ProjectUpload.file storage with settings (avoid absolute dev paths from 0001_initial).

import apps.uploads.models
import django.core.files.storage
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uploads', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='projectupload',
            name='file',
            field=models.FileField(
                max_length=500,
                storage=django.core.files.storage.FileSystemStorage(
                    location=str(settings.STUDENT_UPLOAD_ROOT),
                ),
                upload_to=apps.uploads.models.upload_to,
            ),
        ),
    ]
