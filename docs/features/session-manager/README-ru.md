# Session Manager (Менеджер сессий)

> **English:** [README.md](README.md)

## Что делает

Session Manager — это runtime, живущий внутри активного разговора. Он отслеживает происходящее в каждый момент — события, key moments, эмоциональное состояние — и производит структурированную запись при закрытии сессии. Сессия переживается в реальном времени, а не реконструируется ретроспективно.

## Ключевые концепции

**`SessionContext`** — начальная конфигурация сессии: ID агента, ID сессии, метаданные о контексте (пользователь, платформа и т.д.).

**`SessionEvent`** — единственное записанное событие в рамках сессии. Может быть сообщением пользователя, ответом агента, вызовом инструмента, внутренним наблюдением или любым другим примечательным событием.

**`KeyMomentInput`** — входная схема для захвата key moment в ходе сессии. Содержит описание, опциональный `FeltSense` и оценку значимости (salience).

**`SessionResult`** — вывод завершённой сессии: резюме, список key moments, eigenstate и временные метки.

**`ActiveSessionSummary`** — лёгкая read-модель текущей активной сессии (для дашбордов и мониторинга).

**`Session`** — полная персистентная запись сессии, объединяющая контекст, события, результат и метаданные.

**Хук `AffectPort`** — опциональный асинхронный хук, вызываемый при каждом `record_event()`. Используется детектором аффекта для обновления аффективного состояния агента в ответ на происходящее.

**`PostWriteScheduler`** — опциональный компонент, ставящий в очередь maintenance-задачи (micro/daily рефлексия, decay значимости) после записи результата сессии. Отделяет закрытие сессии от фоновой обработки.

**Восстановление после сбоев** — при включённом журнальном восстановлении `SessionManager` пишет долговременный лог событий в ходе сессии. Если процесс упал до завершения `finish_session`, сессия может быть восстановлена из журнала при следующем запуске.

## Публичный API

```python
class SessionManager:
    async def start_session(self, context: SessionContext) -> Session: ...
    async def record_event(self, session_id: str, event: SessionEvent) -> None: ...
    async def append_key_moment(self, session_id: str, input: KeyMomentInput) -> KeyMoment: ...
    async def finish_session(self, session_id: str) -> SessionResult: ...
    async def get_active_summary(self, session_id: str) -> ActiveSessionSummary | None: ...
```

`finish_session` производит `Eigenstate` — снапшот когнитивного и аффективного состояния агента на момент окончания сессии, — который сохраняется вместе с результатом сессии и питает контекст следующей сессии.

## Конфигурация

Session Manager собирается через `factory.py`. Опциональные компоненты включаются через переменные окружения:

```bash
# Включить интеграцию skill manager
ATMAN_SKILLS_ENABLED=1

# Включить GLiNER+MiniLM детектор аффекта
ATMAN_LINGUISTIC_ENABLED=1

# Лог сессии для отладки
ATMAN_SESSION_LOG=~/.atman/session.log
```

## Пример использования

```bash
make demo-session
```

Программное использование:

```python
context = SessionContext(agent_id="agent-001", session_id="sess-42")
session = await session_manager.start_session(context)

# В ходе разговора
await session_manager.record_event(session.session_id, SessionEvent(
    type="user_message",
    content="Я борюсь с этим уже несколько недель.",
))

# Агент решает, что это значимо
await session_manager.append_key_moment(session.session_id, KeyMomentInput(
    description="Пользователь раскрыл длительную борьбу — высокий эмоциональный вес.",
    salience=0.9,
))

# Конец разговора
result = await session_manager.finish_session(session.session_id)
print(result.eigenstate)
```
