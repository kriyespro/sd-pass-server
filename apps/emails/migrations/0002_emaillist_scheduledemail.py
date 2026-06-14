from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('emails', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.CharField(blank=True, max_length=500)),
                ('emails', models.TextField(blank=True, help_text='One email address per line')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Email List',
                'verbose_name_plural': 'Email Lists',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ScheduledEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('to_emails', models.TextField(blank=True, help_text='One email per line (used if no list selected)')),
                ('scheduled_at', models.DateTimeField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], db_index=True, default='pending', max_length=10)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('error_msg', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_emails', to='emails.emailtemplate')),
                ('email_list', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scheduled_emails', to='emails.emaillist')),
            ],
            options={
                'verbose_name': 'Scheduled Email',
                'verbose_name_plural': 'Scheduled Emails',
                'ordering': ['scheduled_at'],
            },
        ),
    ]
