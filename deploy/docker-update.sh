#!/usr/bin/env bash
# =============================================================
#  OSKOLCTF — обновление через Docker (пересборка образа)
#  Запускай от root: sudo bash deploy/docker-update.sh
# =============================================================
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запускай от root"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

info "Пересобираем образ и перезапускаем..."
docker compose up -d --build

success "Обновление завершено!"
echo -e "  Логи: docker compose logs -f"
