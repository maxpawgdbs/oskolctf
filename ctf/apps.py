from django.apps import AppConfig


class CtfConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ctf"
    verbose_name = "OSKOLCTF"

    def ready(self):
        from ctf.admin_site import ctf_admin_site  # noqa: F401 — регистрирует модели
