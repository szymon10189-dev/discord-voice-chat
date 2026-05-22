"""Status online użytkowników (zielony/czerwony) — licznik aktywnych połączeń WebSocket."""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_connection_counts: dict[int, int] = defaultdict(int)


def user_connected(user_id: int) -> bool:
    """Zwiększa licznik połączeń. Zwraca True, gdy użytkownik właśnie przeszedł na online."""
    with _lock:
        _connection_counts[user_id] += 1
        return _connection_counts[user_id] == 1


def user_disconnected(user_id: int) -> bool:
    """Zmniejsza licznik. Zwraca True, gdy użytkownik właśnie przeszedł na offline."""
    with _lock:
        if user_id not in _connection_counts:
            return False
        _connection_counts[user_id] -= 1
        if _connection_counts[user_id] <= 0:
            del _connection_counts[user_id]
            return True
        return False


def is_user_online(user_id: int) -> bool:
    with _lock:
        return _connection_counts.get(user_id, 0) > 0


def online_user_ids() -> set[int]:
    with _lock:
        return set(_connection_counts.keys())
