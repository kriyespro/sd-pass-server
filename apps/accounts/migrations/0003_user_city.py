from django.db import migrations, models


def add_city_column(apps, schema_editor):
    """Add city only when missing (safe if column was created manually on prod)."""
    connection = schema_editor.connection
    table = 'accounts_user'
    column = 'city'

    with connection.cursor() as cursor:
        existing = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }
    if column in existing:
        return

    field = models.CharField(blank=True, max_length=120)
    field.set_attributes_from_name(column)
    schema_editor.add_field(
        apps.get_model('accounts', 'User'),
        field,
    )


def remove_city_column(apps, schema_editor):
    connection = schema_editor.connection
    table = 'accounts_user'
    column = 'city'

    with connection.cursor() as cursor:
        existing = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }
    if column not in existing:
        return

    field = models.CharField(blank=True, max_length=120)
    field.set_attributes_from_name(column)
    schema_editor.remove_field(
        apps.get_model('accounts', 'User'),
        field,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_manager_email'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_city_column, remove_city_column),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='city',
                    field=models.CharField(blank=True, max_length=120),
                ),
            ],
        ),
    ]
