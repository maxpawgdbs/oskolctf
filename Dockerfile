FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Исходники
COPY . .

# Папка для SQLite базы (монтируется как volume)
RUN mkdir -p /data && \
    # Если база уже есть в образе — переносим в /data (первый запуск)
    if [ -f /app/ctf.sqlite3 ]; then mv /app/ctf.sqlite3 /data/ctf.sqlite3; fi

EXPOSE 8005

CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8005", \
     "--access-logfile", "-", "--error-logfile", "-", "main:app"]
