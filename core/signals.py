from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .bootstrap import add_user_to_default_server, ensure_server_roles
from .models import Server

User = get_user_model()


@receiver(post_save, sender=Server)
def create_default_server_roles(sender, instance: Server, created: bool, **kwargs) -> None:
    ensure_server_roles(instance)


@receiver(post_save, sender=User)
def add_new_user_to_default_server(
    sender,
    instance: User,
    created: bool,
    **kwargs,
) -> None:
    if created:
        add_user_to_default_server(instance)
