"""Logika dostępu do serwerów, ról i moderacji."""

from django.db.models import Q

from .models import Server, ServerBan, ServerMember, ServerRole


def user_servers_qs(user):
    """Serwery, do których użytkownik ma dostęp (właściciel lub członek)."""
    if not user.is_authenticated:
        return Server.objects.none()
    return Server.objects.filter(
        Q(owner=user) | Q(memberships__user=user),
    ).distinct().order_by("name")


def user_has_server_access(user, server: Server) -> bool:
    if not user.is_authenticated:
        return False
    if server.owner_id == user.id:
        return True
    return ServerMember.objects.filter(server=server, user=user).exists()


def get_server_role_kind(user, server: Server) -> str | None:
    """Rola użytkownika na serwerze (tekst RoleKind) lub None. Właściciel = admin."""
    if not user.is_authenticated:
        return None
    if server.owner_id == user.id:
        return ServerRole.RoleKind.ADMIN
    membership = (
        ServerMember.objects.filter(server=server, user=user)
        .select_related("role")
        .first()
    )
    return membership.role.kind if membership else None


def user_is_server_admin(user, server: Server) -> bool:
    """Admin serwera: właściciel lub rola Admin w członkostwie."""
    if not user.is_authenticated:
        return False
    kind = get_server_role_kind(user, server)
    return kind == ServerRole.RoleKind.ADMIN


def user_can_moderate(user, server: Server) -> bool:
    """Moderator lub Admin (w tym właściciel) — usuwanie wiadomości, blokowanie."""
    if not user.is_authenticated:
        return False
    kind = get_server_role_kind(user, server)
    return kind in (
        ServerRole.RoleKind.ADMIN,
        ServerRole.RoleKind.MODERATOR,
    )


def user_is_blocked_on_server(user, server: Server) -> bool:
    if not user.is_authenticated:
        return True
    return ServerBan.objects.filter(server=server, blocked_user=user).exists()


def moderator_can_block_user(actor, server: Server, target) -> bool:
    """Reguły: nie siebie, nie właściciela; moderator tylko User; admin (+ owner) User i Moderator."""
    if not actor.is_authenticated or target is None:
        return False
    if actor.pk == target.pk:
        return False
    if server.owner_id == target.pk:
        return False
    if not user_can_moderate(actor, server):
        return False
    target_kind = get_server_role_kind(target, server)
    if target_kind is None:
        return False
    actor_kind = get_server_role_kind(actor, server)
    if actor_kind == ServerRole.RoleKind.ADMIN:
        return target_kind in (
            ServerRole.RoleKind.USER,
            ServerRole.RoleKind.MODERATOR,
        )
    if actor_kind == ServerRole.RoleKind.MODERATOR:
        return target_kind == ServerRole.RoleKind.USER
    return False
