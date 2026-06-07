from django.db import migrations


def seed_server_options(apps, schema_editor):
    ResellServerOption = apps.get_model('resell', 'ResellServerOption')
    plans = [
        ('test_plan', 'Starter Trial', 'Starter Trial — 1 website · ₹299 · 30 days', 299),
        ('launch_lite', 'Launch Lite', 'Launch Lite — 1 website · ₹1,499/year', 1499),
        ('starter_cloud', 'Starter Cloud', 'Starter Cloud — 1 website · ₹2,099/year', 2099),
        ('wordpress_pro', 'WordPress Pro', 'WordPress Pro — 1 website + 1 Flask app · ₹3,699/year', 3699),
        ('business_cloud', 'Business Cloud', 'Business Cloud — 5 websites · 1 Flask app · ₹5,999/year', 5999),
        ('agency_turbo', 'Agency Turbo', 'Agency Turbo — 10 websites · 3 Flask apps · ₹8,499/year', 8499),
        ('performance_max', 'Performance Max', 'Performance Max — Unlimited websites · 5 Flask apps · ₹11,999/year', 11999),
        ('flask_addon', 'Flask Add-on', 'Flask Add-on — +1 Flask app slot · ₹1,499/year', 1499),
    ]
    for idx, (slug, name, description, price) in enumerate(plans):
        ResellServerOption.objects.update_or_create(
            plan_slug=slug,
            defaults={
                'name': name,
                'description': description,
                'price': price,
                'sort_order': idx,
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('resell', '0004_resellproduct_images_and_servers'),
    ]

    operations = [
        migrations.RunPython(seed_server_options, migrations.RunPython.noop),
    ]
