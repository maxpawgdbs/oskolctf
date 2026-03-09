@echo off
pushd "%~dp0"

:: Создаём venv если нет
if not exist ".venv\Scripts\python.exe" (
    echo [*] Создаём виртуальное окружение...
    python -m venv .venv
)

:: Активируем и устанавливаем зависимости
echo [*] Устанавливаем зависимости...
.venv\Scripts\pip install -q -r requirements.txt

:: Применяем миграции БД
echo [*] Применяем миграции...
.venv\Scripts\python manage.py migrate --noinput

:: Синхронизируем задачи из tasks.json
echo [*] Синхронизируем задачи...
.venv\Scripts\python manage.py sync_tasks

:: Создаём суперюзеров (nekoty, shellovx, gdbs)
echo [*] Создаём суперюзеров...
.venv\Scripts\python manage.py create_superusers

:: Запускаем Django dev-сервер
echo [*] Запуск сайта на http://127.0.0.1:8005
echo [*] Суперюзеры: nekoty / shellovx / gdbs  (пароль: ChangeMe123! — смени через /admin/)
.venv\Scripts\python manage.py runserver 0.0.0.0:8005

popd
