#!/bin/bash
# Atman Stack Autostart Script
# Запускает инфраструктуру Atman (PostgreSQL через Docker) и проверяет
# доступность LLM endpoint (llama-server :8081).
#
# llama-server и embedding-модели Atman 2026 не поднимает автоматически:
# llama-server обычно держит оператор отдельно (контроль над GGUF-файлами /
# параметрами CUDA). Этот скрипт только проверяет, что endpoint жив, и
# подсказывает команду запуска, если нет.

set -e

ATMAN_DIR="${ATMAN_DIR:-/mnt/nvme/atman/atman}"
LLM_ENDPOINT="${ATMAN_LLM_BASE_URL:-http://localhost:8081/v1}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}[Atman] Запуск сервисов...${NC}"

# 1. Запуск Docker (WSL2 способ)
if ! docker info &>/dev/null; then
    echo "[Atman] Запуск Docker..."
    sudo service docker start >/dev/null 2>&1 || true
    sleep 3
fi

# 2. Запуск контейнеров (Postgres; Qdrant пропускается если ATMAN_USE_QDRANT≠1)
cd "${ATMAN_DIR}"
if [ -f "docker-compose.yml" ]; then
    if [ "${ATMAN_USE_QDRANT:-0}" = "1" ]; then
        echo "[Atman] Запуск PostgreSQL + Qdrant..."
        docker compose up -d --remove-orphans
    else
        echo "[Atman] Запуск PostgreSQL (Qdrant отключён; ATMAN_USE_QDRANT=1 чтобы поднять)..."
        docker compose up -d --remove-orphans postgres
    fi
fi

# 3. Проверка LLM endpoint (llama-server :8081)
if curl -sf "${LLM_ENDPOINT}/models" >/dev/null 2>&1; then
    echo -e "${GREEN}[Atman] LLM endpoint жив: ${LLM_ENDPOINT}${NC}"
else
    echo -e "${RED}[Atman] LLM endpoint ${LLM_ENDPOINT} не отвечает!${NC}"
    echo "  Поднимите llama-server с gemma4 (или другим OpenAI-compat сервером), например:"
    echo "    llama-server -m /path/to/gemma4.gguf --host 127.0.0.1 --port 8081 --jinja"
    echo "  Подробнее: atman_agent_cli/RUNBOOK.md → 'Concrete example — gemma4 on :8081'"
fi

echo -e "${GREEN}[Atman] Готово.${NC}"
echo "  • PostgreSQL:  localhost:5432"
echo "  • LLM:         ${LLM_ENDPOINT}"
echo ""
echo "Проверка миграций: .venv/bin/python scripts/run_migrations.py --status"
