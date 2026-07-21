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
            user = User.objects.filter(username=username).first()
            if user is None:
                User.objects.create_superuser(
                    username=username,
                    password=password,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Суперпользователь '{username}' создан"
                ))
            else:
                changed = []
                if not user.is_staff:
                    user.is_staff = True
                    changed.append("is_staff")
                if not user.is_superuser:
                    user.is_superuser = True
                    changed.append("is_superuser")
                if not user.is_active:
                    user.is_active = True
                    changed.append("is_active")
                if changed:
                    user.save(update_fields=changed)
                    self.stdout.write(self.style.SUCCESS(
                        f"'{username}' восстановлен как суперпользователь"
                    ))
                else:
                    self.stdout.write(f"'{username}' уже суперпользователь")
