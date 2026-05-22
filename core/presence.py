"""Status online użytkowników (zielony/czerwony) — WebSocket + ostatnia aktywność HTTP."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_connection_counts: dict[int, int] = defaultdict(int)
_last_activity: dict[int, float] = {}

SITE_PRESENCE_GROUP = "site_presence"
# Po ostatnim żądaniu HTTP użytkownik nadal „online” przez ten czas (sekundy).
ACTIVITY_TIMEOUT_SECONDS = 300


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


def touch_user_activity(user_id: int) -> None:
    """Oznacza aktywność przy żądaniach HTTP (profil, wyszukiwarka itd.)."""
    with _lock:
        _last_activity[user_id] = time.monotonic()


def is_user_online(user_id: int) -> bool:
    with _lock:
        if _connection_counts.get(user_id, 0) > 0:
            return True
        last = _last_activity.get(user_id)
        if last is None:
            return False
        return (time.monotonic() - last) < ACTIVITY_TIMEOUT_SECONDS


def online_user_ids() -> set[int]:
    with _lock:
        return set(_connection_counts.keys())
