from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Server, ServerRole


@receiver(post_save, sender=Server)
def create_default_server_roles(sender, instance: Server, created: bool, **kwargs) -> None:
    if not created:
        return
    defaults = [
        (ServerRole.RoleKind.ADMIN, "Admin"),
        (ServerRole.RoleKind.MODERATOR, "Moderator"),
        (ServerRole.RoleKind.USER, "User"),
    ]
    for kind, label in defaults:
        ServerRole.objects.get_or_create(
            server=instance,
            kind=kind,
            defaults={"name": label},
        )
