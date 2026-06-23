# Тестовая среда

> Автоматически генерируется командой `make codemap`. Не редактировать.

## Обзор

По умолчанию все тесты запускаются без внешних сервисов (in-memory адаптеры).
Тесты PostgreSQL / Ollama пропускаются, если не задана соответствующая переменная окружения или маркер.

## Маркеры тестов

| Маркер | Назначение | Условие пропуска |
|--------|-----------|------------------|
| *(нет)* | Юнит-тест — без внешних зависимостей | Всегда запускается |
| `slow` | Долгоиграющий тест | `-m "not slow"` |
| `integration` | Несколько реальных компонентов, без моков | Требуется полный стек |
| `e2e` | Полный end-to-end сценарий | Требуется агент + LLM |
| `requires_ollama` | Нужен запущенный Ollama | `OLLAMA_HOST` не задан |
| `requires_llm` | Нужен внутренний LLM Atman | `ATMAN_LLM_BASE_URL` не задан |
| `requires_agent_llm` | Нужен LLM агента | `AGENT_LLM_BASE_URL` не задан |

## Запуск тестов

```bash
# Полный прогон (как в CI)
uv run pytest tests/ -v --cov=atman --cov-fail-under=90

# Быстро (без медленных тестов)
uv run pytest tests/ -m "not slow" -v

# Только интеграционные
uv run pytest tests/ -m "integration" -v

# Один файл
uv run pytest tests/path/to/test_foo.py -v
```

## Покрытие

Минимальный порог покрытия: **89%** (временно снижен с 90%; см. `pyproject.toml`).
Источник покрытия: `src/atman/`.
Несколько файлов исключены из покрытия (точки входа CLI, Postgres-адаптеры, требующие БД, тяжёлые ML-адаптеры).

## In-Memory адаптеры, используемые в тестах

| Адаптер | Реализует |
|---------|-----------|
| `InMemoryBackend` | `FactualMemory` |
| `InMemoryStateStore` | `StateStore` |
| `InMemoryEntityRegistry` | `EntityRegistry` |
| `InMemoryMaintenanceQueue` | `MaintenanceQueue` |
| `InMemoryMemoryGuardian` | `MemoryGuardian` |
| `MockEmbeddingAdapter` | `EmbeddingPort` |
| `MockReflectionModel` | `ReflectionModel` |
| `NoOpLinguisticAnalyzer` | `LinguisticAnalyzer` |
| `NoOpReranker` | `MemoryReranker` |
