# Тестовое окружение

> Автоматически сгенерировано командой `make codemap`. Не редактировать вручную.

## Обзор

По умолчанию все тесты запускаются без внешних сервисов (in-memory адаптеры).
Тесты для PostgreSQL и Ollama пропускаются, если соответствующая переменная окружения или маркер не установлены.

## Маркеры тестов

| Маркер | Значение | Условие пропуска |
|--------|----------|-----------------|
| *(нет)* | Юнит-тест — без внешних зависимостей | Всегда запускается |
| `slow` | Долгий тест | `-m "not slow"` |
| `integration` | Несколько реальных компонентов, без моков | Требует полного стека |
| `e2e` | Полный end-to-end сценарий | Требует агента + LLM |
| `requires_ollama` | Нужен запущенный Ollama | `OLLAMA_HOST` не задан |
| `requires_llm` | Нужен внутренний LLM Atman | `ATMAN_LLM_BASE_URL` не задан |
| `requires_agent_llm` | Нужен LLM агента | `AGENT_LLM_BASE_URL` не задан |

## Запуск тестов

```bash
# Полный набор (режим CI)
uv run pytest tests/ -v --cov=atman --cov-fail-under=90

# Быстрый (без медленных тестов)
uv run pytest tests/ -m "not slow" -v

# Только интеграционные
uv run pytest tests/ -m "integration" -v

# Один файл
uv run pytest tests/path/to/test_foo.py -v
```

## Покрытие

Минимальный порог покрытия: **89%** (временно снижен с 90%; см. `pyproject.toml`).
Источник покрытия: `src/atman/`.
Несколько файлов исключены из покрытия (CLI точки входа, Postgres-адаптеры, требующие БД, тяжёлые ML-адаптеры).

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
