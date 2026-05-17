from django.db import migrations, models


def add_sites_scanned_column(apps, schema_editor):
    """Add sites_scanned only when missing (safe if column already exists on prod)."""
    connection = schema_editor.connection
    table = 'platform_ops_assetoptimizationrun'
    column = 'sites_scanned'

    with connection.cursor() as cursor:
        existing = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }
    if column in existing:
        return

    field = models.PositiveIntegerField(
        default=0,
        help_text='Static sites with any files on disk',
    )
    field.set_attributes_from_name(column)
    schema_editor.add_field(
        apps.get_model('platform_ops', 'AssetOptimizationRun'),
        field,
    )


def remove_sites_scanned_column(apps, schema_editor):
    connection = schema_editor.connection
    table = 'platform_ops_assetoptimizationrun'
    column = 'sites_scanned'

    with connection.cursor() as cursor:
        existing = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }
    if column not in existing:
        return

    field = models.PositiveIntegerField(default=0)
    field.set_attributes_from_name(column)
    schema_editor.remove_field(
        apps.get_model('platform_ops', 'AssetOptimizationRun'),
        field,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('platform_ops', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_sites_scanned_column, remove_sites_scanned_column),
            ],
            state_operations=[
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
            ],
        ),
    ]
