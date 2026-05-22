"""Obecność użytkowników w kanałach głosowych (pojedyncza instancja serwera / InMemory layer)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


_presence: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)


def voice_join(
    channel_id: int,
    user_id: int,
    *,
    channel_name: str,
    username: str,
) -> None:
    _presence[channel_id][user_id] = {
        "user_id": user_id,
        "username": username,
        "channel_name": channel_name,
    }


def voice_leave(channel_id: int, user_id: int) -> None:
    if channel_id in _presence:
        _presence[channel_id].pop(user_id, None)
        if not _presence[channel_id]:
            del _presence[channel_id]


def voice_peer_list(channel_id: int, exclude_user_id: int | None = None) -> list[dict[str, Any]]:
    peers = []
    for uid, data in _presence.get(channel_id, {}).items():
        if exclude_user_id is not None and uid == exclude_user_id:
            continue
        peers.append(
            {
                "user_id": data["user_id"],
                "username": data["username"],
            }
        )
    peers.sort(key=lambda p: p["username"].lower())
    return peers


def voice_channel_name_for_user(channel_id: int, user_id: int) -> str | None:
    entry = _presence.get(channel_id, {}).get(user_id)
    if not entry:
        return None
    return entry.get("channel_name")
