from django import template

from ..presence import is_user_online

register = template.Library()


@register.filter(name="dict_get")
def dict_get(mapping, key):
    if not mapping:
        return []
    try:
        return mapping.get(int(key), mapping.get(key, []))
    except (TypeError, ValueError):
        return mapping.get(key, [])


@register.filter(name="user_online")
def user_online(user_or_id) -> bool:
    if user_or_id is None:
        return False
    user_id = getattr(user_or_id, "pk", user_or_id)
    try:
        return is_user_online(int(user_id))
    except (TypeError, ValueError):
        return False
