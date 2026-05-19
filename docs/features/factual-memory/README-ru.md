# Factual Memory (Фактическая память)

> **English:** [README.md](README.md)

## Что делает

Factual Memory хранит проверяемые дискретные факты о мире — то, что агент знает как истину о людях, местах, событиях или о себе. Это не интерпретации, не чувства, не нарратив: это проверяемые утверждения.

Факты сохраняются между сессиями. При начале новой сессии `PassiveMemoryInjector` инжектирует релевантные факты в контекст агента через embedding similarity и BM25 поиск.

## Ключевые концепции

**`FactRecord`** — единственный проверяемый факт. Содержит текст факта, источник, достоверность и временные метки. Имеет версию схемы для совместимости.

**`Relation`** — типизированная направленная связь между двумя сущностями (например, `Человек A работает_в Компания B`). Хранится вместе с фактами и используется реестром сущностей для построения рассуждений о связях.

**Порт `FactualMemory`** — интерфейс, который реализуют все бэкенды. Доменная логика зависит только от этого интерфейса, никогда от конкретного бэкенда.

**Обнаружение конфликтов** — `ConflictDetector` может сканировать факты на предмет противоречий и выводить их для разрешения.

## Публичный API

Порт `FactualMemory` определяет:

```python
class FactualMemory(ABC):
    async def add(self, fact: FactRecord) -> str: ...
    async def get(self, fact_id: str) -> FactRecord | None: ...
    async def search(self, query: str, limit: int = 10) -> list[FactRecord]: ...
    async def delete(self, fact_id: str) -> None: ...
    async def list_all(self) -> list[FactRecord]: ...
```

## Конфигурация

Выберите бэкенд через переменную окружения `ATMAN_MEMORY_BACKEND`:

| Значение | Бэкенд | Примечания |
|----------|--------|-----------|
| `inmemory` | `InMemoryBackend` | Эфемерный, сбрасывается при перезапуске. Подходит для тестов. |
| `file` | `FileBackend` | JSONL-файл в рабочей директории. По умолчанию. |
| `postgres` | `PostgresFactualMemory` | Требует `ATMAN_DB_URL` и `atman[eval]`. |

При использовании бэкенда `postgres` задайте одно из:

```bash
ATMAN_DB_URL=postgresql://atman:secret@localhost:5432/atman
# или
DATABASE_URL=postgresql://atman:secret@localhost:5432/atman
```

## Пример использования

Запуск интерактивного REPL:

```bash
atman
```

Запуск демо:

```bash
make demo-factual
```

Программное использование:

```python
from atman.config import build_memory_backend

backend = build_memory_backend()  # читает ATMAN_MEMORY_BACKEND из env

fact = FactRecord(text="Алиса — ведущий инженер.", source="onboarding")
fact_id = await backend.add(fact)

results = await backend.search("ведущий инженер")
```
