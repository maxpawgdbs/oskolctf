#!/usr/bin/env bash
# =============================================================
#  OSKOLCTF — обновление через Docker (git pull + пересборка)
#  Запускай от root: sudo bash deploy/docker-update.sh
# =============================================================
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}[*]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запускай от root: sudo bash deploy/docker-update.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── 1. git pull ──────────────────────────────────────────────
if [[ -d .git ]]; then
    info "Получаем последний код из git..."
    # Сохраняем .env и data/ — они не трекаются, но на всякий случай
    git fetch --all
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    git reset --hard origin/"$BRANCH"
    success "Код обновлён (ветка: $BRANCH)"
else
    warn "Папка .git не найдена — пропускаем git pull"
fi

# ── 2. Пересборка и перезапуск контейнеров ───────────────────
info "Пересобираем образ и перезапускаем контейнеры..."
docker compose up -d --build --remove-orphans

# ── 3. Ждём старта и показываем статус ───────────────────────
sleep 3
docker compose ps

success "Обновление завершено!"
echo -e "  Логи:  docker compose logs -f"
echo -e "  Стоп:  docker compose down"
