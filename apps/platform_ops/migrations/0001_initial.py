import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AssetOptimizationRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('next_run_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('projects_processed', models.PositiveIntegerField(default=0)),
                ('css_files', models.PositiveIntegerField(default=0)),
                ('js_files', models.PositiveIntegerField(default=0)),
                ('image_files', models.PositiveIntegerField(default=0)),
                ('files_optimized', models.PositiveIntegerField(default=0)),
                ('bytes_before', models.BigIntegerField(default=0)),
                ('bytes_after', models.BigIntegerField(default=0)),
                ('bytes_saved', models.BigIntegerField(default=0)),
                ('cache_used_memory_human', models.CharField(blank=True, max_length=64)),
                ('cache_peak_memory_human', models.CharField(blank=True, max_length=64)),
                ('cache_keys', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('triggered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asset_optimization_runs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
        migrations.CreateModel(
            name='PlatformBackup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('backup_type', models.CharField(choices=[('full', 'Full (database + sites)'), ('database', 'Database only'), ('sites', 'Student sites only')], default='full', max_length=20)),
                ('storage_path', models.CharField(blank=True, max_length=500)),
                ('size_bytes', models.BigIntegerField(default=0)),
                ('includes_database', models.BooleanField(default=True)),
                ('includes_sites', models.BooleanField(default=True)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='platform_backups', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
