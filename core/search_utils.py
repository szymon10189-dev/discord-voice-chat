"""Wyszukiwanie kanałów i użytkowników."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .bootstrap import SYSTEM_USERNAME
from .models import Channel, Server
from .services import user_has_server_access, user_servers_qs

User = get_user_model()

SEARCH_MIN_LEN = 2
SEARCH_MAX_CHANNELS = 40
SEARCH_MAX_USERS = 25


def search_for_viewer(
    viewer,
    query: str,
    *,
    server: Server | None = None,
) -> dict:
    """
    Zwraca dopasowane kanały (tekst/głos) i użytkowników serwerów,
    do których viewer ma dostęp.
    """
    q = (query or "").strip()
    empty = {
        "query": q,
        "text_channels": [],
        "voice_channels": [],
        "users": [],
    }
    if len(q) < SEARCH_MIN_LEN:
        return empty

    if server is not None:
        if not user_has_server_access(viewer, server):
            return empty
        servers = Server.objects.filter(pk=server.pk)
    else:
        servers = user_servers_qs(viewer)

    if not servers.exists():
        return empty

    channels = (
        Channel.objects.filter(server__in=servers, name__icontains=q)
        .select_related("server")
        .order_by("server__name", "channel_type", "name")[:SEARCH_MAX_CHANNELS]
    )
    text_channels = [ch for ch in channels if ch.is_text]
    voice_channels = [ch for ch in channels if ch.is_voice]

    users = (
        User.objects.filter(
            server_memberships__server__in=servers,
            username__icontains=q,
        )
        .exclude(username=SYSTEM_USERNAME)
        .exclude(pk=viewer.pk)
        .distinct()
        .order_by("username")[:SEARCH_MAX_USERS]
    )

    return {
        "query": q,
        "text_channels": text_channels,
        "voice_channels": voice_channels,
        "users": list(users),
    }


def server_members_for_sidebar(server: Server):
    """Aktywni członkowie serwera (bez konta system) — do listy w sidebarze."""
    return (
        User.objects.filter(server_memberships__server=server, is_active=True)
        .exclude(username=SYSTEM_USERNAME)
        .order_by("username")
    )
