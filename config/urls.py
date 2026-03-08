from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    # Django admin отключён — используй /ctf-admin/
    # Обратная совместимость: /css/ → раздаём из BASE_DIR/css/
    re_path(r"^css/(?P<path>.*)$", serve, {"document_root": settings.BASE_DIR / "css"}),
    # Media (аватарки) — всегда, не только в DEBUG
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path("", include("ctf.urls")),
]
