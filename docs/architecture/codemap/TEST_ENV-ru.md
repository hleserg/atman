# Тестовое окружение

> Автоматически сгенерировано `make codemap`. Не редактировать.

## Обзор

По умолчанию все тесты запускаются без внешних сервисов (in-memory адаптеры).
Тесты для PostgreSQL / Ollama пропускаются, если не установлена соответствующая переменная окружения или маркер.

## Маркеры тестов

| Маркер | Значение | Условие пропуска |
|--------|---------|----------------|
| *(нет)* | Юнит-тест — без внешних зависимостей | Всегда выполняется |
| `slow` | Долго выполняющийся тест | `-m "not slow"` |
| `integration` | Несколько реальных компонентов, без моков | Требует полный стек |
| `e2e` | Полный сквозной (e2e) сценарий | Требует агента + LLM |
| `requires_ollama` | Требует запущенный экземпляр Ollama | `OLLAMA_HOST` не задан |
| `requires_llm` | Требует внутренний LLM Atman | `ATMAN_LLM_BASE_URL` не задан |
| `requires_agent_llm` | Требует LLM агента | `AGENT_LLM_BASE_URL` не задан |

## Запуск тестов

```bash
# Full suite (CI style)
uv run pytest tests/ -v --cov=atman --cov-fail-under=90

# Fast (skip slow tests)
uv run pytest tests/ -m "not slow" -v

# Integration only
uv run pytest tests/ -m "integration" -v

# Single file
uv run pytest tests/path/to/test_foo.py -v
```

## Покрытие

Минимальный порог покрытия: **89%** (временно снижен с 90%; см. `pyproject.toml`).
Источник покрытия: `src/atman/`.
Несколько файлов исключены из покрытия (точки входа CLI, Postgres-адаптеры, требующие БД, тяжёлые ML-адаптеры).

## In-memory адаптеры, используемые в тестах

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
