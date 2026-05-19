# Установка Atman

> **English version:** [INSTALLATION.md](INSTALLATION.md)

## Требования

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| Python | 3.11+ | Runtime |
| [uv](https://github.com/astral-sh/uv) | последняя | Управление окружением и зависимостями |
| Docker + Docker Compose | 24+ | PostgreSQL (опционально) |
| llama.cpp (`llama-server`) или Ollama | — | LLM для рефлексии |

Установка uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Установка зависимостей

Клонируйте репозиторий и установите зависимости:

```bash
git clone https://github.com/your-org/atman.git
cd atman

# Создать виртуальное окружение и установить пакет в режиме разработки
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Для production без dev-инструментов:

```bash
uv pip install atman
```

Для production с eval-инфраструктурой (Alembic, PostgreSQL):

```bash
uv pip install "atman[eval]"
```

## Docker сервисы

PostgreSQL запускается через Docker Compose (опционально — только если используется `ATMAN_MEMORY_BACKEND=postgres`):

```bash
# Запустить PostgreSQL в фоне
docker compose up -d postgres

# Проверить статус
docker compose ps
```

`docker-compose.yml` в корне репозитория содержит сервис `postgres` с настройками по умолчанию из `.env`.

Применить миграции схемы:

```bash
# Требует atman[eval]
uv run alembic upgrade head
```

## Настройка LLM

Atman работает с любым OpenAI-совместимым LLM-эндпоинтом.

### Вариант A: llama-server (llama.cpp)

```bash
llama-server \
  --model /path/to/gemma3-27b-it-qat.gguf \
  --port 8081 \
  --ctx-size 8192
```

Установите переменную:

```bash
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat
```

### Вариант B: Ollama

```bash
ollama serve
ollama pull gemma3:27b
```

Установите переменную:

```bash
ATMAN_LLM_BASE_URL=http://localhost:11434/v1
ATMAN_LLM_MODEL=gemma3:27b
```

Для эмбеддингов через Ollama:

```bash
ollama pull bge-m3
EMBEDDING_BACKEND=ollama
EMBEDDING_OLLAMA_HOST=http://localhost:11434
```

## Конфигурация

Скопируйте шаблон переменных окружения:

```bash
cp .env.example .env
```

Отредактируйте `.env`, заполнив необходимые значения:

```bash
# Обязательно
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat

# Бэкенд памяти (по умолчанию: file — PostgreSQL не нужен)
ATMAN_MEMORY_BACKEND=file

# Бэкенд эмбеддингов (по умолчанию: ollama)
EMBEDDING_BACKEND=ollama
EMBEDDING_OLLAMA_HOST=http://localhost:11434
```

Полный список переменных с описанием — в файле `.env.example`.

## Первый запуск

Проверьте установку:

```bash
atman --help
```

Запустите REPL фактической памяти:

```bash
atman
```

Запустите рефлексию вручную:

```bash
python -m atman.cli_reflection reflect micro --agent-id <uuid>
```

Запустите демо:

```bash
make demo-factual
make demo-experience
```

## Проверка

Запустите тесты:

```bash
uv run pytest tests/ -v
```

Выполните проверку кода:

```bash
make check
```

Для проверки подключения к LLM:

```bash
curl http://localhost:8081/v1/models
```

Для проверки подключения к Ollama:

```bash
curl http://localhost:11434/api/tags
```
