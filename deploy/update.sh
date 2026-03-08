#!/usr/bin/env bash
# =============================================================
#  OSKOLCTF — обновление уже установленного сайта
#  Запускай от root: sudo bash update.sh
# =============================================================
set -euo pipefail

PROJECT_DIR="/opt/oskolctf"
SERVICE_NAME="oskolctf"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запускай от root: sudo bash update.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

info "Копируем обновлённые файлы..."
rsync -a --exclude='.venv' --exclude='__pycache__' \
         --exclude='*.pyc'  --exclude='.git' \
         --exclude='ctf.sqlite3' \
         "$SOURCE_DIR/" "$PROJECT_DIR/"

info "Обновляем зависимости..."
"$PROJECT_DIR/.venv/bin/pip" install -q --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"

chown -R www-data:www-data "$PROJECT_DIR"

info "Перезапускаем сервис..."
systemctl restart "$SERVICE_NAME"

success "Обновление завершено!"
echo -e "  Логи: journalctl -u $SERVICE_NAME -f"
