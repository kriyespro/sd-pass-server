from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AffiliateApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('website', models.URLField(blank=True, help_text='Your main website or channel URL.')),
                ('platform', models.CharField(
                    choices=[
                        ('youtube', 'YouTube'), ('instagram', 'Instagram'),
                        ('twitter', 'Twitter / X'), ('linkedin', 'LinkedIn'),
                        ('blog', 'Blog / Website'), ('tiktok', 'TikTok'), ('other', 'Other'),
                    ],
                    default='other', max_length=20,
                )),
                ('audience_size', models.CharField(blank=True, help_text='Approximate followers/subscribers (e.g. 5000, 10k).', max_length=30)),
                ('message', models.TextField(help_text='Why do you want to become an affiliate? How will you promote StudentCloud?', max_length=1000)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                    db_index=True, default='pending', max_length=20,
                )),
                ('admin_notes', models.TextField(blank=True, help_text='Internal notes (not shown to applicant).')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Affiliate Application',
                'verbose_name_plural': 'Affiliate Applications',
                'ordering': ['-created_at'],
            },
        ),
    ]
