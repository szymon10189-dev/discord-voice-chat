import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

_should_serve_media = settings.DEBUG or getattr(settings, "SERVE_MEDIA", False)
if _should_serve_media:
    if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    else:
        media_prefix = settings.MEDIA_URL.lstrip("/").rstrip("/")
        if media_prefix:
            urlpatterns += [
                re_path(
                    rf"^{re.escape(media_prefix)}/(?P<path>.*)$",
                    serve,
                    {"document_root": settings.MEDIA_ROOT},
                ),
            ]

handler404 = "core.views.page_not_found_view"
