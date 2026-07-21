#!/bin/sh
set -e

# Если tasks.json — директория (Docker создал её при отсутствии файла на хосте),
# удаляем и создаём пустой массив
if [ -d "/app/tasks.json" ]; then
    echo "[!] /app/tasks.json — директория, исправляем..."
    rm -rf /app/tasks.json
    echo "[]" > /app/tasks.json
fi
# Если файла нет вообще — создаём
if [ ! -f "/app/tasks.json" ]; then
    echo "[]" > /app/tasks.json
fi

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
