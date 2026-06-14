from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('emails', '0002_emaillist_scheduledemail'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('frequency', models.CharField(choices=[('weekly', 'Weekly'), ('biweekly', 'Every 2 Weeks'), ('monthly', 'Monthly')], max_length=20)),
                ('next_run_at', models.DateTimeField()),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaigns', to='emails.emailtemplate')),
                ('email_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaigns', to='emails.emaillist')),
            ],
            options={
                'verbose_name': 'Email Campaign',
                'verbose_name_plural': 'Email Campaigns',
                'ordering': ['next_run_at'],
            },
        ),
    ]
