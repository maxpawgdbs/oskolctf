#!/bin/sh
set -e

echo "[*] Применяем миграции..."
python manage.py migrate --noinput

echo "[*] Собираем статику..."
python manage.py collectstatic --noinput --clear 2>/dev/null || python manage.py collectstatic --noinput

echo "[*] Синхронизируем задачи из tasks.json..."
python manage.py sync_tasks 2>/dev/null || echo "[!] sync_tasks пропущен (возможно, таблица ещё пустая)"

echo "[*] Создаём суперюзеров..."
python manage.py create_superusers 2>/dev/null || echo "[!] Суперюзеры уже существуют"

echo "[*] Запускаем gunicorn..."
exec gunicorn config.wsgi:application \
    --workers 2 \
    --bind 0.0.0.0:8005 \
    --access-logfile - \
    --error-logfile -
