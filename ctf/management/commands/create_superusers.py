"""
Management-команда: create_superusers
Создаёт предустановленных суперпользователей: nekoty, shellovx, gdbs.
"""
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model

User = get_user_model()

SUPERUSER_NAMES = ["nekoty", "shellovx", "gdbs"]


class Command(BaseCommand):
    help = "Создаёт предустановленных суперпользователей (nekoty, shellovx, gdbs)"

    def handle(self, *args, **options):
        password = os.environ.get("SUPERUSER_PASSWORD")
        if not password:
            if settings.DEBUG:
                password = "ChangeMe123!"
            else:
                raise CommandError("SUPERUSER_PASSWORD must be set when DEBUG=0")
        for username in SUPERUSER_NAMES:
            if not User.objects.filter(username=username).exists():
                User.objects.create_superuser(
                    username=username,
                    password=password,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Суперпользователь '{username}' создан"
                ))
            else:
                self.stdout.write(f"'{username}' уже существует — пропуск")
