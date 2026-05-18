from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_project_site_subfolder'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectSubfolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(blank=True, default='', max_length=64)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subfolders',
                    to='projects.project',
                )),
            ],
            options={
                'ordering': ['path'],
                'unique_together': {('project', 'path')},
            },
        ),
    ]
