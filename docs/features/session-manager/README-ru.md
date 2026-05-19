# Session Manager (Менеджер сессий)

> **English:** [README.md](README.md)

## Что делает

Session Manager — это runtime, живущий внутри активного разговора. Он отслеживает происходящее в каждый момент — события, key moments, эмоциональное состояние — и производит структурированную запись при закрытии сессии. Сессия переживается в реальном времени, а не реконструируется ретроспективно.

## Ключевые концепции

**`SessionContext`** — начальная конфигурация сессии: ID агента, ID сессии, метаданные о контексте (пользователь, платформа и т.д.).

**`SessionEvent`** — единственное записанное событие в рамках сессии. Может быть сообщением пользователя, ответом агента, вызовом инструмента, внутренним наблюдением или любым другим примечательным событием.

**`KeyMomentInput`** — входная схема для захвата key moment в ходе сессии. Обязательные поля: `what_happened`, `emotional_valence`, `emotional_intensity`, `depth`, `why_it_matters`.

**`SessionResult`** — вывод завершённой сессии: резюме, список key moments, eigenstate и временные метки.

**`ActiveSessionSummary`** — лёгкая read-модель текущей активной сессии (для дашбордов и мониторинга).

**`Session`** — полная персистентная запись сессии, объединяющая контекст, события, результат и метаданные.

**Хук `AffectPort`** — опциональный асинхронный хук, вызываемый при каждом `record_event()`. Используется детектором аффекта для обновления аффективного состояния агента в ответ на происходящее.

**`PostWriteScheduler`** — опциональный компонент, ставящий в очередь maintenance-задачи (micro/daily рефлексия, decay значимости) после записи результата сессии. Отделяет закрытие сессии от фоновой обработки.

**Восстановление после сбоев** — при включённом журнальном восстановлении `SessionManager` пишет долговременный лог событий в ходе сессии. Если процесс упал до завершения `finish_session`, сессия может быть восстановлена из журнала при следующем запуске.

## Публичный API

```python
class SessionManager:
    def start_session(self, agent_id: UUID) -> SessionContext: ...
    def record_event(self, session_id: UUID, event: SessionEvent) -> None: ...
    def append_key_moment(self, session_id: UUID, moment: KeyMoment) -> None: ...
    def append_key_moment_input(self, session_id: UUID, moment: KeyMomentInput) -> None: ...
    def finish_session(self, session_id: UUID, overall_emotional_tone: float = 0.0, key_insight: str = "", close_reason: str | None = None) -> SessionResult: ...
```

Все методы синхронные.

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
from uuid import UUID

agent_id = UUID("...")

# Начало сессии — возвращает SessionContext с identity_snapshot_id
ctx = session_manager.start_session(agent_id)

# В ходе разговора — запись событий
session_manager.record_event(ctx.session_id, SessionEvent(
    session_id=ctx.session_id,
    event_type="user_message",
    description="Я борюсь с этим уже несколько недель.",
))

# Агент решает, что это значимо
session_manager.append_key_moment_input(ctx.session_id, KeyMomentInput(
    what_happened="Пользователь раскрыл длительную борьбу — высокий эмоциональный вес.",
    emotional_valence=-0.5,
    emotional_intensity=0.9,
    depth=EmotionalDepth.deep,
    why_it_matters="Пользователь раскрыл уязвимость; важно для доверия.",
))

# Конец разговора
result = session_manager.finish_session(ctx.session_id)
print(result.eigenstate)
```
