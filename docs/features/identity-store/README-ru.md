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
    def bootstrap_identity(self, agent_id: UUID) -> Identity: ...
    def get_identity(self, agent_id: UUID) -> Identity | None: ...
    def add_core_value(self, agent_id: UUID, value: CoreValue) -> Identity: ...
    def add_principle(self, agent_id: UUID, principle: Principle) -> Identity: ...
    def add_habit(self, agent_id: UUID, habit: Habit) -> Identity: ...
    def add_goal(self, agent_id: UUID, goal: Goal) -> Identity: ...
    def create_snapshot(self, agent_id: UUID, description: str) -> IdentitySnapshot: ...
    def apply_self_change(self, agent_id: UUID, target_kind: SelfChangeTargetKind, payload: Any, source: SelfChangeSource) -> SelfAppliedChange: ...
    def revert_self_change(self, agent_id: UUID, change_id: UUID) -> Identity: ...
```

Все методы синхронные. `apply_self_change` и `revert_self_change` вызываются `DeepReflectionService`, когда модель рефлексии предлагает изменения в самопонимании агента.

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
from uuid import UUID

agent_id = UUID("...")

# Инициализация идентичности нового агента
identity = identity_service.bootstrap_identity(agent_id)

# Просмотр текущих ценностей
for value in identity.core_values:
    print(value.name, value.confidence)

# Снапшот перед применением изменений рефлексии
snapshot = identity_service.create_snapshot(agent_id, description="до рефлексии")

# Добавление нового принципа
identity = identity_service.add_principle(
    agent_id,
    Principle(statement="Всегда уточнять перед предположениями.")
)
```
