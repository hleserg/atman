# Identity Store (Хранилище идентичности)

> **English:** [README.md](README.md)

## Что делает

Identity Store — структурированное самопредставление агента. Здесь хранится то, что агент считает истинным о себе: его ценности, привычки, принципы, цели и открытые вопросы. Идентичность не статична — она эволюционирует через рефлексию и может обновляться в ответ на то, что агент узнаёт о себе.

## Ключевые концепции

**`Identity`** — корневая запись. Агрегирует все компоненты идентичности для данного агента.

**`CoreValue`** — фундаментальная ценность агента (например, честность, забота, точность). Ценности имеют вес и не меняются легко.

**`Habit`** — повторяющийся поведенческий паттерн, позитивный или негативный. Наблюдается со временем через опыт.

**`Principle`** — actionable правило, выведенное из ценностей (например, «Всегда уточнять перед предположениями»).

**`Goal`** — текущая цель, над которой работает агент. Может быть краткосрочной или долгосрочной.

**`OpenQuestion`** — то, в чём агент реально не уверен, отслеживается для постоянной рефлексии.

**`IdentitySnapshot`** — замороженная копия полного состояния идентичности в момент времени. Создаётся перед обновлениями рефлексии, чтобы их можно было откатить.

**`HelpfulnessLevel`** — структурированный дескриптор текущего расположения агента к полезности.

## Публичный API

`IdentityService` управляет полным жизненным циклом:

```python
class IdentityService:
    async def bootstrap(self, agent_id: str) -> Identity: ...
    async def get(self, agent_id: str) -> Identity: ...
    async def update(self, agent_id: str, patch: dict) -> Identity: ...
    async def snapshot(self, agent_id: str) -> IdentitySnapshot: ...
    async def apply_self_change(self, agent_id: str, change: dict) -> Identity: ...
    async def revert_self_change(self, agent_id: str, snapshot_id: str) -> Identity: ...
```

`apply_self_change` и `revert_self_change` вызываются `DeepReflectionService`, когда модель рефлексии предлагает изменения в самопонимании агента.

Идентичность хранится через порт `StateStore`.

## Конфигурация

Использует общий бэкенд `StateStore`:

| `ATMAN_MEMORY_BACKEND` | Бэкенд |
|------------------------|--------|
| `inmemory` | `InMemoryStateStore` |
| `file` (по умолчанию) | `FileStateStore` — один JSON-файл на запись идентичности |
| `postgres` | `PostgresStateStore` |

## Пример использования

```bash
# Запуск демо идентичности
make demo-identity

# CLI
python -m atman.cli_identity
```

Программное использование:

```python
# Инициализация идентичности нового агента
identity = await identity_service.bootstrap(agent_id="agent-001")

# Просмотр текущих ценностей
for value in identity.core_values:
    print(value.name, value.weight)

# Снапшот перед применением изменений рефлексии
snapshot = await identity_service.snapshot(agent_id)

# Применение self-change, предложенного рефлексией
updated = await identity_service.apply_self_change(
    agent_id,
    change={"add_habit": {"name": "Проверять допущения заранее", "valence": "positive"}}
)

# Откат при необходимости
reverted = await identity_service.revert_self_change(agent_id, snapshot.snapshot_id)
```
