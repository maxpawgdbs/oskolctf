"""
Management-команда: create_superusers
Создаёт предустановленных суперпользователей: nekoty, shellovx, gdbs.
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

SUPERUSERS = [
    {"username": "nekoty", "password": os.environ.get("SUPERUSER_PASSWORD", "ChangeMe123!")},
    {"username": "shellovx", "password": os.environ.get("SUPERUSER_PASSWORD", "ChangeMe123!")},
    {"username": "gdbs", "password": os.environ.get("SUPERUSER_PASSWORD", "ChangeMe123!")},
]


class Command(BaseCommand):
    help = "Создаёт предустановленных суперпользователей (nekoty, shellovx, gdbs)"

    def handle(self, *args, **options):
        for su in SUPERUSERS:
            if not User.objects.filter(username=su["username"]).exists():
                User.objects.create_superuser(
                    username=su["username"],
                    password=su["password"],
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Суперпользователь '{su['username']}' создан"
                ))
            else:
                self.stdout.write(f"'{su['username']}' уже существует — пропуск")
