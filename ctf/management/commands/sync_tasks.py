"""
sync_tasks — синхронизирует tasks.json с базой данных.
Используется при деплое: python manage.py sync_tasks
"""
from django.core.management.base import BaseCommand
from ctf.models import sync_tasks_from_json


class Command(BaseCommand):
    help = "Синхронизирует tasks.json → таблица Task в БД"

    def handle(self, *args, **options):
        created, updated = sync_tasks_from_json()
        self.stdout.write(self.style.SUCCESS(
            f"Синхронизация выполнена: создано {created}, обновлено {updated}"
        ))
