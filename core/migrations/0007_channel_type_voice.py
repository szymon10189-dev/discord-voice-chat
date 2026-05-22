from django.db import migrations, models


def ensure_voice_channels(apps, schema_editor):
    Channel = apps.get_model("core", "Channel")
    Server = apps.get_model("core", "Server")
    for server in Server.objects.all():
        Channel.objects.get_or_create(
            server=server,
            name="ogólny",
            channel_type="text",
        )
        Channel.objects.get_or_create(
            server=server,
            name="ogólny-głos",
            channel_type="voice",
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_direct_message_reactions"),
    ]

    operations = [
        migrations.AddField(
            model_name="channel",
            name="channel_type",
            field=models.CharField(
                choices=[("text", "Tekstowy"), ("voice", "Głosowy")],
                default="text",
                max_length=10,
            ),
        ),
        migrations.AlterModelOptions(
            name="channel",
            options={"ordering": ["channel_type", "name"]},
        ),
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(
                fields=("server", "name", "channel_type"),
                name="core_channel_unique_name_per_type",
            ),
        ),
        migrations.RunPython(ensure_voice_channels, noop),
    ]
