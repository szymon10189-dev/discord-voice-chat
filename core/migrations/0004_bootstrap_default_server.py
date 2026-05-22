from django.contrib.auth.hashers import make_password
from django.db import migrations

DEFAULT_SERVER_NAME = "Serwer główny"
DEFAULT_CHANNEL_NAME = "ogólny"
SYSTEM_USERNAME = "system"

ROLE_DEFINITIONS = (
    ("admin", "Admin"),
    ("moderator", "Moderator"),
    ("user", "User"),
)


def bootstrap(apps, schema_editor):
    User = apps.get_model("core", "User")
    Server = apps.get_model("core", "Server")
    Channel = apps.get_model("core", "Channel")
    ServerRole = apps.get_model("core", "ServerRole")
    ServerMember = apps.get_model("core", "ServerMember")

    system_user, created = User.objects.get_or_create(
        username=SYSTEM_USERNAME,
        defaults={
            "email": "system@discord-clone.local",
            "is_active": False,
            "is_staff": False,
        },
    )
    if created:
        system_user.password = make_password(None)
        system_user.save(update_fields=["password"])

    server, _ = Server.objects.get_or_create(
        name=DEFAULT_SERVER_NAME,
        defaults={"owner_id": system_user.pk},
    )

    for kind, label in ROLE_DEFINITIONS:
        ServerRole.objects.get_or_create(
            server=server,
            kind=kind,
            defaults={"name": label},
        )

    Channel.objects.get_or_create(
        server=server,
        name=DEFAULT_CHANNEL_NAME,
    )

    user_role = ServerRole.objects.get(server=server, kind="user")
    for user in User.objects.exclude(username=SYSTEM_USERNAME):
        ServerMember.objects.get_or_create(
            server=server,
            user=user,
            defaults={"role_id": user_role.pk},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_direct_messages"),
    ]

    operations = [
        migrations.RunPython(bootstrap, noop),
    ]
