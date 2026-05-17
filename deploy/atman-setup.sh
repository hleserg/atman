#!/usr/bin/env bash
# =============================================================================
# Atman Memory Stack — полный деплой
# Требования: Ubuntu 22.04+ в WSL2, uv установлен, sudo доступ
# Использование: bash atman-setup.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${CYAN}[atman]${NC} $*"; }
ok()     { echo -e "${GREEN}[✓]${NC} $*"; }
warn()   { echo -e "${YELLOW}[!]${NC} $*"; }
error()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}"; }
info()   { echo -e "    ${BLUE}→${NC} $*"; }

# ── Конфигурация ─────────────────────────────────────────────────────────────
ATMAN_DIR="${HOME}/.atman"
SECRETS_FILE="${ATMAN_DIR}/.secrets"
POSTGRES_VERSION="16"
POSTGRES_DB="atman"
POSTGRES_USER="atman"
POSTGRES_PORT="5432"
QDRANT_PORT="6333"
QDRANT_VERSION="latest"

# Atman LLM endpoint defaults (overridable via env/.env).
# Atman 2026 uses one OpenAI-compatible endpoint (llama-server :8081 + gemma4)
# for both user-agent (pydantic-ai) and internal reflection.
: "${ATMAN_LLM_BASE_URL:=http://localhost:8081/v1}"
: "${LLM_MODEL:=gemma4}"
: "${EMBEDDING_FLAG_MODEL:=BAAI/bge-m3}"

# NVMe путь — скрипт определит автоматически или использует дефолт
NVME_PATH=""
DOCKER_DATA_PATH=""

# ── Баннер ───────────────────────────────────────────────────────────────────
clear
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         Atman Memory Stack Setup             ║"
echo "  ║                                              ║"
echo "  ║  PostgreSQL 16 + pgvector                    ║"
echo "  ║  llama-server :8081  ·  gemma4               ║"
echo "  ║  FlagEmbedding (bge-m3, bge-reranker-v2-m3)  ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Начало: $(date '+%Y-%m-%d %H:%M:%S')\n"

# ── 1. Проверки окружения ─────────────────────────────────────────────────────
header "Шаг 1 / 10 — Проверка окружения"

# WSL2?
if grep -qi microsoft /proc/version 2>/dev/null; then
    ok "WSL2 обнаружен"
else
    warn "Не похоже на WSL2 — продолжаю как обычный Linux"
fi

# sudo
sudo -n true 2>/dev/null || sudo true
ok "sudo доступен"

# uv
if ! command -v uv &>/dev/null; then
    log "uv не найден — устанавливаю..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
    ok "uv установлен"
else
    ok "uv $(uv --version | awk '{print $2}')"
fi

# Docker
if ! command -v docker &>/dev/null; then
    log "Docker не найден — устанавливаю Docker Engine..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker "${USER}"
    ok "Docker установлен"
else
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

# Запуск Docker
if ! sudo systemctl is-active --quiet docker 2>/dev/null; then
    sudo systemctl enable --now docker > /dev/null 2>&1 || true
    sleep 2
fi

# Проверяем доступ к Docker без sudo
if ! docker ps &>/dev/null; then
    warn "Docker требует sudo — добавляю в группу docker"
    sudo usermod -aG docker "${USER}" 2>/dev/null || true
    DOCKER_CMD="sudo docker"
else
    DOCKER_CMD="docker"
fi
ok "Docker daemon запущен"

# Базовые утилиты
log "Устанавливаю зависимости..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    curl wget openssl python3 python3-pip \
    lsblk util-linux systemd git \
    > /dev/null 2>&1
ok "Базовые утилиты готовы"

# ── 2. Определяем NVMe диск ──────────────────────────────────────────────────
header "Шаг 2 / 10 — Определение хранилища"

log "Сканирую доступные диски..."
echo ""
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL 2>/dev/null || lsblk
echo ""

# Ищем NVMe автоматически
NVME_DEVICE=$(lsblk -d -o NAME,TYPE 2>/dev/null | grep -i nvme | awk '{print $1}' | head -1)
NVME_SIZE=$(lsblk -d -o NAME,SIZE 2>/dev/null | grep -i nvme | awk '{print $2}' | head -1)

if [[ -n "${NVME_DEVICE}" ]]; then
    # Проверяем есть ли партиции
    NVME_PARTITION=$(lsblk -o NAME,TYPE 2>/dev/null | grep "part" | grep -i nvme | awk '{print $1}' | head -1)
    
    if [[ -n "${NVME_PARTITION}" ]]; then
        # Проверяем смонтирован ли
        NVME_MOUNT=$(lsblk -o NAME,MOUNTPOINT 2>/dev/null | grep "${NVME_PARTITION}" | awk '{print $2}')
        if [[ -n "${NVME_MOUNT}" && "${NVME_MOUNT}" != "/" ]]; then
            NVME_PATH="${NVME_MOUNT}"
            ok "NVMe найден: /dev/${NVME_DEVICE} (${NVME_SIZE}) → смонтирован в ${NVME_PATH}"
        fi
    fi
fi

if [[ -z "${NVME_PATH}" ]]; then
    # Ищем большой диск смонтированный не как /
    ALT_MOUNT=$(lsblk -o MOUNTPOINT,SIZE 2>/dev/null | grep -v "^/" | grep -v "MOUNTPOINT" | grep -v "^$" | sort -rh | head -1 | awk '{print $1}')
    if [[ -n "${ALT_MOUNT}" ]]; then
        NVME_PATH="${ALT_MOUNT}"
        warn "NVMe не найден, использую: ${NVME_PATH}"
    else
        NVME_PATH="${HOME}"
        warn "Отдельный диск не найден — использую домашнюю директорию: ${NVME_PATH}"
    fi
fi

# Пути для данных
# HF_HOME — куда FlagEmbedding/transformers/gliner будут кэшировать веса HF Hub.
HF_HOME="${NVME_PATH}/atman/hf"
DOCKER_DATA_PATH="${NVME_PATH}/atman/docker"
ATMAN_DATA_PATH="${NVME_PATH}/atman/data"
PG_BACKUP_PATH="${NVME_PATH}/atman/backups"

log "Создаю директории на ${NVME_PATH}..."
mkdir -p "${HF_HOME}"
mkdir -p "${DOCKER_DATA_PATH}"
mkdir -p "${ATMAN_DATA_PATH}"
mkdir -p "${PG_BACKUP_PATH}"
ok "Директории созданы в ${NVME_PATH}/atman/"

# Переносим Docker data-root если не там
CURRENT_DOCKER_ROOT=$(docker info 2>/dev/null | grep "Docker Root Dir" | awk '{print $4}' || echo "/var/lib/docker")
if [[ "${CURRENT_DOCKER_ROOT}" != "${DOCKER_DATA_PATH}" && "${NVME_PATH}" != "${HOME}" ]]; then
    log "Переношу Docker data-root на NVMe..."
    sudo systemctl stop docker 2>/dev/null || true
    sudo mkdir -p "${DOCKER_DATA_PATH}"
    if [[ -d "/var/lib/docker" ]]; then
        sudo rsync -a /var/lib/docker/ "${DOCKER_DATA_PATH}/" 2>/dev/null || true
    fi
    sudo tee /etc/docker/daemon.json > /dev/null << EOF
{
  "data-root": "${DOCKER_DATA_PATH}",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
    sudo systemctl start docker
    sleep 3
    ok "Docker data-root → ${DOCKER_DATA_PATH}"
fi

# ── 3. Секреты ────────────────────────────────────────────────────────────────
header "Шаг 3 / 10 — Генерация секретов"

mkdir -p "${ATMAN_DIR}"
chmod 700 "${ATMAN_DIR}"

if [[ ! -f "${SECRETS_FILE}" ]]; then
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
    POSTGRES_APP_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
    QDRANT_API_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)

    cat > "${SECRETS_FILE}" << EOF
# Atman secrets — не коммитить в git!
# Создан: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Postgres ─────────────────────────────────────────────────────────────────
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_APP_PASSWORD=${POSTGRES_APP_PASSWORD}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_HOST=localhost
POSTGRES_PORT=${POSTGRES_PORT}
# atman — admin/superuser (миграции); atman_app — non-superuser (рантайм, RLS)
DATABASE_URL=postgresql://atman_app:${POSTGRES_APP_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}
ATMAN_ADMIN_DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}

# ── LLM (один endpoint на user-agent и reflection) ───────────────────────────
# llama-server c gemma4 (или другой OpenAI-compat) на :8081.
ATMAN_REFLECTION_BACKEND=openai
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_API_KEY=dummy
LLM_MODEL=gemma4

# pydantic-ai user-agent (тот же endpoint)
AGENT_LLM_BASE_URL=http://localhost:8081/v1
AGENT_LLM_API_KEY=dummy
AGENT_LLM_MODEL=gemma4

# ── Embeddings + reranker — native FlagEmbedding на CPU ──────────────────────
EMBEDDING_BACKEND=flag
EMBEDDING_FLAG_MODEL=BAAI/bge-m3

# ── Storage paths ────────────────────────────────────────────────────────────
NVME_PATH=${NVME_PATH}

# ── Qdrant (НЕ ИСПОЛЬЗУЕТСЯ; контейнер можно выключить) ──────────────────────
# QDRANT_URL=http://localhost:${QDRANT_PORT}
# QDRANT_API_KEY=${QDRANT_API_KEY}

# ── Ollama (ВЫПИЛЕНА; оставлено для миграции старых конфигов) ────────────────
# OLLAMA_URL=http://localhost:11434
EOF
    chmod 600 "${SECRETS_FILE}"
    ok "Секреты сгенерированы → ${SECRETS_FILE}"
else
    warn "Секреты уже существуют — использую существующие"
fi

source "${SECRETS_FILE}"

# .env в проекте
if [[ -f "pyproject.toml" ]]; then
    cp "${SECRETS_FILE}" "./.env"
    chmod 600 "./.env"
    ok ".env создан в $(pwd)"
fi

# ── 4. Ollama ─────────────────────────────────────────────────────────────────
header "Шаг 4 / 10 — LLM endpoint (llama-server :8081)"

# Atman больше не использует Ollama — все LLM-вызовы идут через OpenAI-compatible
# endpoint, по умолчанию llama-server на :8081 с gemma4. Embeddings/reranker —
# через native FlagEmbedding (см. шаг 10). Этот шаг только проверяет, что
# endpoint доступен; запуск llama-server остаётся на ответственности оператора
# (см. atman_agent_cli/RUNBOOK.md → "Запуск llama-server :8081").

LLM_ENDPOINT="${ATMAN_LLM_BASE_URL:-http://localhost:8081/v1}"
log "Проверяю LLM endpoint: ${LLM_ENDPOINT}"
if curl -sf "${LLM_ENDPOINT}/models" > /dev/null 2>&1; then
    MODELS_JSON=$(curl -s "${LLM_ENDPOINT}/models" 2>/dev/null || echo "")
    ok "LLM endpoint жив (${LLM_ENDPOINT})"
    info "Доступные модели: $(echo "${MODELS_JSON}" | python3 -c \
        'import sys,json; d=json.load(sys.stdin); print(", ".join(m["id"] for m in d.get("data",[])))' \
        2>/dev/null || echo "не удалось распарсить ответ")"
else
    warn "LLM endpoint ${LLM_ENDPOINT} не отвечает."
    warn "Поднимите llama-server (или другой OpenAI-compat сервер) c gemma4 перед запуском Atman."
    warn "Пример: llama-server -m <gemma4.gguf> --host 127.0.0.1 --port 8081 --jinja"
    warn "Продолжаю установку — endpoint можно поднять позже."
fi

# ── 5. Pre-warm native ML моделей (опционально) ─────────────────────────────
header "Шаг 5 / 10 — Native CPU модели (lazy, опциональный pre-warm)"

# FlagEmbedding (bge-m3 + bge-reranker), gliner, transformers (MiniLM, mREBEL)
# скачиваются с Hugging Face Hub при первом обращении адаптера. Не блокирующий
# шаг: если нужно прогреть до старта, запустите вручную:
#   .venv/bin/python scripts/measure_native_models_cold_start.py
info "ML-модели lazy-load с HF Hub (BAAI/bge-m3, BAAI/bge-reranker-v2-m3,"
info "  urchade/gliner_multi-v2.1, MoritzLaurer/...-MiniLMv2..., Babelscape/mrebel-large)"
ok "Pre-warm пропущен — модели подтянутся при первом запросе"

# ── 6. PostgreSQL + pgvector ──────────────────────────────────────────────────
header "Шаг 6 / 10 — PostgreSQL 16 + pgvector"

PG_VOLUME="atman-postgres-data"
PG_CONTAINER="atman-postgres"

if ${DOCKER_CMD} ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    warn "Контейнер ${PG_CONTAINER} уже существует"
    ${DOCKER_CMD} start "${PG_CONTAINER}" > /dev/null 2>&1 || true
else
    log "Запускаю PostgreSQL..."
    ${DOCKER_CMD} run -d \
        --name "${PG_CONTAINER}" \
        --restart unless-stopped \
        -e POSTGRES_USER="${POSTGRES_USER}" \
        -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
        -e POSTGRES_DB="${POSTGRES_DB}" \
        -e POSTGRES_INITDB_ARGS="--encoding=UTF-8 --lc-collate=C --lc-ctype=C" \
        -p "127.0.0.1:${POSTGRES_PORT}:5432" \
        -v "${PG_VOLUME}:/var/lib/postgresql/data" \
        -v "${PG_BACKUP_PATH}:/backups" \
        "pgvector/pgvector:pg${POSTGRES_VERSION}" \
        > /dev/null
    ok "Контейнер создан"
fi

log "Жду готовности PostgreSQL..."
RETRIES=30
until ${DOCKER_CMD} exec "${PG_CONTAINER}" \
    pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    [[ $RETRIES -eq 0 ]] && error "PostgreSQL не запустился"
    sleep 1
done
ok "PostgreSQL готов"

# ── 7. Схема БД (через scripts/run_migrations.py) ────────────────────────────
header "Шаг 7 / 10 — Накат миграций"

# Раннер на Python требует venv с psycopg. Поднимаем venv заранее (минимальный,
# полный набор зависимостей встаёт в шаге 10).
if [[ ! -d ".venv" ]]; then
    log "Создаю минимальный venv для раннера миграций..."
    if command -v uv &>/dev/null; then
        uv venv --python 3.12 > /dev/null 2>&1 || uv venv > /dev/null 2>&1
        uv pip install --quiet "psycopg[binary]" > /dev/null
    else
        python3 -m venv .venv
        .venv/bin/python -m pip install --quiet --upgrade pip > /dev/null
        .venv/bin/python -m pip install --quiet "psycopg[binary]" > /dev/null
    fi
fi

# Передаём пароль atman_app раннеру через env, чтобы он сделал ALTER USER
# (DATABASE_URL уже содержит правильный пароль; раннер парсит его).
log "Применяю scripts/bootstrap_db.sql + migrations/versions/* через раннер..."
.venv/bin/python scripts/run_migrations.py

TABLE_COUNT=$(${DOCKER_CMD} exec "${PG_CONTAINER}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
ok "Схема создана: ${TABLE_COUNT} объектов в public.* (плюс agent_N схемы)"

# ── 8. Qdrant (опционально — по умолчанию пропускается) ─────────────────────
header "Шаг 8 / 10 — Qdrant (skip-by-default)"

# Atman 2026 использует Postgres+pgvector как vector store. Qdrant остался
# как unused dependency и контейнер запускается ТОЛЬКО если ATMAN_USE_QDRANT=1.
if [[ "${ATMAN_USE_QDRANT:-0}" == "1" ]]; then
    QDRANT_CONTAINER="atman-qdrant"
    log "ATMAN_USE_QDRANT=1 — поднимаю Qdrant..."
    if ${DOCKER_CMD} ps -a --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER}$"; then
        warn "Контейнер ${QDRANT_CONTAINER} уже существует"
        ${DOCKER_CMD} start "${QDRANT_CONTAINER}" > /dev/null 2>&1 || true
    else
        ${DOCKER_CMD} run -d \
            --name "${QDRANT_CONTAINER}" \
            --restart unless-stopped \
            -p "127.0.0.1:${QDRANT_PORT}:6333" \
            -p "127.0.0.1:6334:6334" \
            -v atman-qdrant-data:/qdrant/storage \
            -e QDRANT__SERVICE__API_KEY="${QDRANT_API_KEY}" \
            "qdrant/qdrant:${QDRANT_VERSION}" \
            > /dev/null
    fi
    RETRIES=30
    until curl -sf "http://localhost:${QDRANT_PORT}/health" > /dev/null 2>&1; do
        RETRIES=$((RETRIES - 1))
        [[ $RETRIES -eq 0 ]] && error "Qdrant не запустился"
        sleep 1
    done
    ok "Qdrant готов"
else
    info "Qdrant пропущен (ATMAN_USE_QDRANT≠1). Для включения: export ATMAN_USE_QDRANT=1"
fi

# ── 9. Docker Compose ─────────────────────────────────────────────────────────
header "Шаг 9 / 10 — Docker Compose"

if [[ -f "pyproject.toml" ]]; then
    COMPOSE_DIR="$(pwd)"
else
    COMPOSE_DIR="${ATMAN_DIR}"
fi

cat > "${COMPOSE_DIR}/docker-compose.yml" << EOF
# Atman infrastructure — запуск: docker compose up -d
# Остановка: docker compose stop
# Удаление: docker compose down

version: '3.9'

services:
  postgres:
    image: pgvector/pgvector:pg${POSTGRES_VERSION}
    container_name: atman-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: \${POSTGRES_USER}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: \${POSTGRES_DB}
    ports:
      - "127.0.0.1:${POSTGRES_PORT}:5432"
    volumes:
      - atman-postgres-data:/var/lib/postgresql/data
      - ${PG_BACKUP_PATH}:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

# qdrant: deprecated — Atman 2026 uses Postgres+pgvector. Раскомментируйте
# только если ATMAN_USE_QDRANT=1.
#  qdrant:
#    image: qdrant/qdrant:${QDRANT_VERSION}
#    container_name: atman-qdrant
#    restart: unless-stopped
#    environment:
#      QDRANT__SERVICE__API_KEY: \${QDRANT_API_KEY}
#    ports:
#      - "127.0.0.1:6333:6333"
#      - "127.0.0.1:6334:6334"
#    volumes:
#      - atman-qdrant-data:/qdrant/storage

volumes:
  atman-postgres-data:
EOF

ok "docker-compose.yml создан → ${COMPOSE_DIR}"

# ── 10. Python зависимости ────────────────────────────────────────────────────
header "Шаг 10 / 10 — Python окружение"

if [[ -f "pyproject.toml" ]]; then
    log "Устанавливаю полный набор Python-зависимостей (dev + linguistic + e2e)..."
    # .venv мог быть создан минимальным в шаге 7 — здесь дополняем.
    if command -v uv &>/dev/null; then
        uv pip install --quiet -e ".[dev,linguistic,e2e]"
    else
        .venv/bin/python -m pip install --quiet -e ".[dev,linguistic,e2e]"
    fi
    ok "Python зависимости установлены"
else
    warn "pyproject.toml не найден — пропускаю Python зависимости"
    info "Запусти скрипт из корня репозитория Atman"
fi

# ── Smoke тест ────────────────────────────────────────────────────────────────
header "Smoke test"

# PostgreSQL
PG_TABLES=$(${DOCKER_CMD} exec "${PG_CONTAINER}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null)
ok "PostgreSQL: ${PG_TABLES} таблиц/объектов"

# pgvector
PG_VEC=$(${DOCKER_CMD} exec "${PG_CONTAINER}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -t -A -c "SELECT extversion FROM pg_extension WHERE extname='vector';" 2>/dev/null)
ok "pgvector: v${PG_VEC}"

# Migrations applied
MIG_COUNT=$(${DOCKER_CMD} exec "${PG_CONTAINER}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -t -A -c "SELECT COUNT(*) FROM public.schema_migrations;" 2>/dev/null)
ok "schema_migrations: ${MIG_COUNT} записей"

# atman_app role + RLS
APP_LOGIN=$(${DOCKER_CMD} exec "${PG_CONTAINER}" \
    bash -c "PGPASSWORD='${POSTGRES_APP_PASSWORD}' psql -h localhost -U atman_app -d ${POSTGRES_DB} -t -A -c 'SELECT current_user;'" 2>/dev/null)
if [[ "${APP_LOGIN}" == "atman_app" ]]; then
    ok "atman_app: успешный логин с RLS"
else
    warn "atman_app: не удалось подключиться (проверьте пароль в .env)"
fi

# LLM endpoint (llama-server)
LLM_MODELS=$(curl -sf "${ATMAN_LLM_BASE_URL:-http://localhost:8081/v1}/models" 2>/dev/null \
    | python3 -c "import sys,json; print(', '.join(m['id'] for m in json.load(sys.stdin).get('data',[])))" 2>/dev/null || echo "")
if [[ -n "${LLM_MODELS}" ]]; then
    ok "LLM endpoint: ${LLM_MODELS}"
else
    warn "LLM endpoint не отвечает — поднимите llama-server :8081"
fi

# ── Итог ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  Atman Memory Stack успешно развёрнут!       ${NC}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Сервисы:${NC}"
echo -e "  ${GREEN}●${NC} PostgreSQL + pgvector → localhost:${POSTGRES_PORT}"
echo -e "  ${GREEN}●${NC} Qdrant               → localhost:${QDRANT_PORT}"
echo -e "  ${GREEN}●${NC} Ollama               → localhost:11434"
echo ""
echo -e "${BOLD}Модели:${NC}"
echo -e "  ${GREEN}●${NC} LLM:        ${LLM_MODEL}  (через llama-server :8081)"
echo -e "  ${GREEN}●${NC} Embed:      ${EMBEDDING_FLAG_MODEL}  (FlagEmbedding native, CPU)"
echo ""
echo -e "${BOLD}Данные:${NC}"
echo -e "  ${GREEN}●${NC} Секреты:    ${SECRETS_FILE}"
echo -e "  ${GREEN}●${NC} .env:       $(pwd)/.env"
echo -e "  ${GREEN}●${NC} Compose:    ${COMPOSE_DIR}/docker-compose.yml"
echo -e "  ${GREEN}●${NC} HF cache:   ${HF_HOME}"
echo -e "  ${GREEN}●${NC} Бэкапы:    ${PG_BACKUP_PATH}"
echo ""
echo -e "${BOLD}Управление:${NC}"
echo -e "  Запуск:    ${CYAN}docker compose up -d${NC}"
echo -e "  Остановка: ${CYAN}docker compose stop${NC}"
echo -e "  Логи PG:   ${CYAN}docker logs atman-postgres${NC}"
echo -e "  Статус:    ${CYAN}docker ps${NC}"
echo ""
echo -e "${BOLD}Следующий шаг:${NC} запустить sanity: python scripts/run_migrations.py --status"
echo ""
echo -e "  Завершено: $(date '+%Y-%m-%d %H:%M:%S')"
