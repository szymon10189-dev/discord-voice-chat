"""
Domyślny serwer, 3 role, kanał oraz członkostwo użytkowników po rejestracji.
"""

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Channel, Server, ServerMember, ServerRole

User = get_user_model()

DEFAULT_SERVER_NAME = "Serwer główny"
DEFAULT_CHANNEL_NAME = "ogólny"
DEFAULT_VOICE_CHANNEL_NAME = "ogólny-głos"
SYSTEM_USERNAME = "system"

ROLE_DEFINITIONS = (
    (ServerRole.RoleKind.ADMIN, "Admin"),
    (ServerRole.RoleKind.MODERATOR, "Moderator"),
    (ServerRole.RoleKind.USER, "User"),
)


def get_or_create_system_user() -> User:
    user, created = User.objects.get_or_create(
        username=SYSTEM_USERNAME,
        defaults={
            "email": "system@discord-clone.local",
            "is_active": False,
            "is_staff": False,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


def ensure_server_roles(server: Server) -> None:
    """Zawsze dokładnie 3 role: Admin, Moderator, User."""
    for kind, label in ROLE_DEFINITIONS:
        ServerRole.objects.get_or_create(
            server=server,
            kind=kind,
            defaults={"name": label},
        )


def ensure_default_server() -> Server:
    owner = get_or_create_system_user()
    server, _ = Server.objects.get_or_create(
        name=DEFAULT_SERVER_NAME,
        defaults={"owner": owner},
    )
    ensure_server_roles(server)
    return server


def ensure_default_channel(server: Server | None = None) -> Channel:
    server = server or ensure_default_server()
    channel, _ = Channel.objects.get_or_create(
        server=server,
        name=DEFAULT_CHANNEL_NAME,
        channel_type=Channel.ChannelType.TEXT,
    )
    return channel


def ensure_default_voice_channel(server: Server | None = None) -> Channel:
    server = server or ensure_default_server()
    channel, _ = Channel.objects.get_or_create(
        server=server,
        name=DEFAULT_VOICE_CHANNEL_NAME,
        channel_type=Channel.ChannelType.VOICE,
    )
    return channel


def ensure_server_channels(server: Server) -> None:
    ensure_default_channel(server)
    ensure_default_voice_channel(server)


def get_default_user_role(server: Server) -> ServerRole:
    ensure_server_roles(server)
    return ServerRole.objects.get(server=server, kind=ServerRole.RoleKind.USER)


def add_user_to_default_server(user: User) -> None:
    """
    Dodaje użytkownika do domyślnego serwera z rolą User.
    Gwarantuje też istnienie kanału tekstowego (#ogólny) i głosowego (ogólny-głos).
    Dostęp do obu kanałów wynika z członkostwa na serwerze.
    """
    if not user.pk or user.username == SYSTEM_USERNAME:
        return
    server = ensure_default_server()
    ensure_server_channels(server)
    role = get_default_user_role(server)
    ServerMember.objects.get_or_create(
        server=server,
        user=user,
        defaults={"role": role},
    )


def get_default_dashboard_redirect_url(user: User) -> str:
    """URL domyślnego kanału tekstowego po logowaniu (z fallbackiem na głosowy / home)."""
    from django.urls import reverse

    from .services import user_has_server_access

    if not user.is_authenticated or not user.pk or user.username == SYSTEM_USERNAME:
        return reverse("core:home")

    add_user_to_default_server(user)
    server = ensure_default_server()

    if not user_has_server_access(user, server):
        return reverse("core:home")

    text_channel = (
        Channel.objects.filter(
            server=server,
            channel_type=Channel.ChannelType.TEXT,
        )
        .order_by("name")
        .first()
    )
    if text_channel:
        return reverse(
            "core:dashboard_channel",
            kwargs={"server_id": server.id, "channel_id": text_channel.id},
        )

    voice_channel = (
        Channel.objects.filter(
            server=server,
            channel_type=Channel.ChannelType.VOICE,
        )
        .order_by("name")
        .first()
    )
    if voice_channel:
        return reverse(
            "core:voice_channel",
            kwargs={"server_id": server.id, "voice_channel_id": voice_channel.id},
        )

    return reverse("core:dashboard", kwargs={"server_id": server.id})


def sync_all_users_to_default_server() -> None:
    """Przypisuje wszystkich istniejących użytkowników do domyślnego serwera."""
    server = ensure_default_server()
    ensure_server_channels(server)
    role = get_default_user_role(server)
    for user in User.objects.exclude(username=SYSTEM_USERNAME):
        ServerMember.objects.get_or_create(
            server=server,
            user=user,
            defaults={"role": role},
        )


@transaction.atomic
def bootstrap_defaults() -> None:
    """Idempotentna inicjalizacja: system, serwer, role, kanały tekstowy i głosowy."""
    server = ensure_default_server()
    ensure_server_channels(server)
