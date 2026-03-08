#!/usr/bin/env bash
# =============================================================
#  OSKOLCTF — Docker-установщик для Debian/Ubuntu VPS
#  Запускай от root: sudo bash deploy/docker-install.sh
# =============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запускай от root: sudo bash deploy/docker-install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── 1. Docker ────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Устанавливаем Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    success "Docker установлен"
else
    success "Docker уже установлен: $(docker --version)"
fi

# ── 2. SECRET_KEY ────────────────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Генерируем SECRET_KEY..."
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(48))")
    echo "SECRET_KEY=$SECRET" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    success "SECRET_KEY сохранён в .env"
else
    info ".env уже существует, оставляем как есть"
fi

# ── 3. Папка для базы данных ─────────────────────────────────
# Пустая папка — база создастся автоматически при первом запуске
mkdir -p "$PROJECT_DIR/data"

# ── 4. Сборка и запуск ───────────────────────────────────────
cd "$PROJECT_DIR"
info "Собираем образ и запускаем контейнеры..."
docker compose up -d --build

# ── Итог ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Установка завершена!${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  Сайт:     http://$(hostname -I | awk '{print $1}')"
echo -e "  Логи:     docker compose logs -f"
echo -e "  Статус:   docker compose ps"
echo ""
echo -e "  HTTPS (опционально):"
echo -e "    apt install certbot"
echo -e "    certbot certonly --standalone -d ВАШ_ДОМЕН"
echo -e "    # затем раскомментируй HTTPS-блок в deploy/nginx.conf"
echo ""
