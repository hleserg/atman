#!/bin/bash
# Atman Stack Autostart Script
# Запускает все сервисы Atman (Docker + Ollama)

set -e

ATMAN_DIR="/mnt/nvme/atman/atman"
OLLAMA_LOG="${HOME}/.atman/ollama.log"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}[Atman] Запуск сервисов...${NC}"

# 1. Запуск Docker (WSL2 способ)
if ! docker info &>/dev/null; then
    echo "[Atman] Запуск Docker..."
    sudo service docker start >/dev/null 2>&1 || true
    sleep 3
fi

# 2. Запуск контейнеров
cd "${ATMAN_DIR}"
if [ -f "docker-compose.yml" ]; then
    echo "[Atman] Запуск PostgreSQL и Qdrant..."
    docker compose up -d --remove-orphans
fi

# 3. Запуск Ollama (если не запущен)
if ! pgrep -x "ollama" >/dev/null; then
    echo "[Atman] Запуск Ollama..."
    mkdir -p "${HOME}/.atman"
    nohup ollama serve > "${OLLAMA_LOG}" 2>&1 &
    sleep 2
fi

echo -e "${GREEN}[Atman] Все сервисы запущены!${NC}"
echo "  • PostgreSQL: localhost:5432"
echo "  • Qdrant: localhost:6333"
echo "  • Ollama: localhost:11434"
echo ""
echo "Проверка: ollama list"
