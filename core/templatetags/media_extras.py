from django import template

from ..media_utils import filefield_url_if_exists

register = template.Library()


@register.filter(name="file_url")
def file_url(filefield):
    """Zwraca URL pliku tylko gdy istnieje w storage — pusty string w przeciwnym razie."""
    return filefield_url_if_exists(filefield)
