from django.db import migrations


def bootstrap(apps, schema_editor):
    from core.bootstrap import sync_all_users_to_default_server

    sync_all_users_to_default_server()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_direct_messages"),
    ]

    operations = [
        migrations.RunPython(bootstrap, noop),
    ]
