#!/usr/bin/env bash
# =============================================================
#  OSKOLCTF — установщик для Debian/Ubuntu VPS
#  Запускай от root: sudo bash install.sh
#  Перед запуском при необходимости поменяй переменные ниже
# =============================================================
set -euo pipefail

# ─── Конфигурация ────────────────────────────────────────────
PROJECT_DIR="/opt/oskolctf"   # куда скопируется проект
PORT=8005                     # внутренний порт gunicorn
DOMAIN="_"                    # домен для nginx (или IP; _ = любой)
SERVICE_NAME="oskolctf"
# ─────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запускай от root: sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"   # папка проекта (родитель deploy/)

# ── 1. Системные пакеты ──────────────────────────────────────
info "Обновляем пакеты и ставим зависимости..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx

# ── 2. Копируем проект ───────────────────────────────────────
info "Копируем проект в $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' \
         --exclude='*.pyc'  --exclude='.git' \
         "$SOURCE_DIR/" "$PROJECT_DIR/"

# ── 3. Virtualenv + зависимости ──────────────────────────────
info "Создаём venv и устанавливаем зависимости..."
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install -q --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"

# ── 4. SECRET_KEY ────────────────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Генерируем SECRET_KEY..."
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(48))")
    echo "SECRET_KEY=$SECRET" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    success "SECRET_KEY сохранён в $ENV_FILE"
else
    info ".env уже существует, оставляем как есть"
fi

# ── 5. Права на папку ────────────────────────────────────────
chown -R www-data:www-data "$PROJECT_DIR"

# ── 6. Systemd-сервис ────────────────────────────────────────
info "Создаём systemd-сервис $SERVICE_NAME ..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=OSKOLCTF Flask App
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${PROJECT_DIR}/.venv/bin/gunicorn \\
    --workers 2 \\
    --bind 127.0.0.1:${PORT} \\
    --access-logfile /var/log/${SERVICE_NAME}-access.log \\
    --error-logfile  /var/log/${SERVICE_NAME}-error.log \\
    main:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
success "Сервис $SERVICE_NAME запущен"

# ── 7. Nginx ─────────────────────────────────────────────────
info "Настраиваем nginx..."
NGINX_CONF="/etc/nginx/sites-available/${SERVICE_NAME}"
cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 16M;

    location / {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60;
    }
}
EOF

ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
# Убираем дефолтный сайт, если есть
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx
success "Nginx настроен"

# ── Итог ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Установка завершена!${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  Сайт:       http://$(hostname -I | awk '{print $1}')"
echo -e "  Проект:     $PROJECT_DIR"
echo -e "  Логи:       journalctl -u $SERVICE_NAME -f"
echo -e "  Ошибки:     tail -f /var/log/${SERVICE_NAME}-error.log"
echo ""
echo -e "  HTTPS (опционально):"
echo -e "    apt install certbot python3-certbot-nginx"
echo -e "    certbot --nginx -d ВАШ_ДОМЕН"
echo ""
