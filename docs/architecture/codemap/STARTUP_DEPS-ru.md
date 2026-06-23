# Зависимости при запуске

> Автоматически генерируется командой `make codemap`. Не редактировать.

## Сервисы Docker Compose

| Сервис | Образ | Порты | Зависит от |
|--------|-------|-------|------------|
| `postgres` | `pgvector/pgvector:pg16` | 127.0.0.1:5432:5432 | — |
| `qdrant` | `qdrant/qdrant:latest` | 127.0.0.1:6333:6333, 127.0.0.1:6334:6334 | — |

## Необходимые переменные окружения

Полный список Pydantic settings — в `src/atman/config.py`.
Ключевые переменные:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ATMAN_MEMORY_BACKEND` | Бэкенд хранилища: `postgres\|file\|inmemory` | `file` |
| `EMBEDDING_BACKEND` | Эмбеддинги: `ollama\|flag\|mock` | `ollama` |
| `ATMAN_LLM_BASE_URL` | LLM endpoint (OpenAI-compatible) | — |
| `ATMAN_OLLAMA_BASE_URL` | Хост Ollama | `http://localhost:11434` |
| `DATABASE_URL` | DSN PostgreSQL (postgres backend) | — |
