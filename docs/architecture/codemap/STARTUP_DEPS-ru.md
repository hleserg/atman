# Зависимости при запуске

> Автоматически сгенерировано командой `make codemap`. Не редактировать вручную.

## Сервисы Docker Compose

| Сервис | Образ | Порты | Зависит от |
|--------|-------|-------|------------|
| `postgres` | `pgvector/pgvector:pg16` | 127.0.0.1:5432:5432 | — |
| `qdrant` | `qdrant/qdrant:latest` | 127.0.0.1:6333:6333, 127.0.0.1:6334:6334 | — |

## Обязательные переменные окружения

Полный список полей Pydantic settings — в `src/atman/config.py`.
Ключевые переменные:

| Переменная | Описание | Значение по умолчанию |
|------------|----------|-----------------------|
| `ATMAN_MEMORY_BACKEND` | Бэкенд хранения: `postgres\|file\|inmemory` | `file` |
| `EMBEDDING_BACKEND` | Эмбеддинги: `ollama\|flag\|mock` | `ollama` |
| `ATMAN_LLM_BASE_URL` | LLM-эндпоинт (OpenAI-совместимый) | — |
| `ATMAN_OLLAMA_BASE_URL` | Хост Ollama | `http://localhost:11434` |
| `DATABASE_URL` | PostgreSQL DSN (бэкенд postgres) | — |
