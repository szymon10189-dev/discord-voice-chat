def filefield_url_if_exists(filefield) -> str:
    """Zwraca publiczny URL pola pliku tylko gdy obiekt istnieje w storage (unika 404 w przeglądarce i w logach)."""
    if filefield is None:
        return ""
    name = getattr(filefield, "name", None) or ""
    if not name:
        return ""
    storage = getattr(filefield, "storage", None)
    if storage is None:
        return ""
    try:
        if storage.exists(name):
            return filefield.url
    except OSError:
        pass
    return ""
