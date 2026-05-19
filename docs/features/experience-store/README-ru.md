# Experience Store (Хранилище опыта)

> **English:** [README.md](README.md)

## Что делает

Experience Store архивирует пережитый опыт агента от первого лица. Здесь хранятся не факты и не анализ, а *то, что агент реально пережил* — текстура взаимодействий, эмоциональный тон, переломные моменты.

Опыты — это сырой материал для рефлексии. `MicroReflectionService` читает их после каждой сессии; `DailyReflectionService` сканирует их на паттерны; `DeepReflectionService` использует для структурного анализа.

## Ключевые концепции

**`KeyMoment`** — самостоятельная запись первого класса, представляющая значимый момент в ходе сессии. Имеет оценку значимости (salience), которая снижается со временем. Два ключевых метода:
- `mark_accessed()` — вызвать при извлечении момента; обновляет временную метку последнего доступа
- `calculate_current_salience(now)` — возвращает текущее значение salience с учётом decay

**`SessionExperience`** — read-only представление закрытой сессии, собранное из её key moments и метаданных. После закрытия сессии не изменяется.

**`FeltSense`** — довербальное, интуитивное ощущение агента от ситуации. Качественный дескриптор, прикреплённый к моментам и опытам.

**`ContextHalo`** — окружающая контекстная информация вокруг сессии: среда, недавнее состояние, внешние факторы.

**`ReframingNote`** — ретроспективная заметка, добавленная к key moment, дающая новую интерпретацию в свете последующих событий. Добавляется через `ReframingNoteAppendResult`.

**`EmotionalDepth`** — структурированный дескриптор эмоционального веса опыта.

**`SalienceDecayService`** — порт, управляющий снижением salience по мере устаревания key moments. Реализация по умолчанию: `InMemorySalienceDecayService`.

## Публичный API

Key moments хранятся через `StateStore`:

```python
class StateStore(ABC):
    def create_key_moment(self, key_moment: KeyMoment) -> KeyMoment: ...
    def store_key_moment(self, key_moment: KeyMoment) -> KeyMoment: ...  # идемпотентный upsert
    def get_key_moment(self, moment_id: UUID) -> KeyMoment | None: ...
    def list_key_moments(self, session_id: UUID | None = None) -> list[KeyMoment]: ...
    def mark_moment_accessed(self, moment_id: UUID) -> None: ...
```

Записи опыта закрытых сессий хранятся через `StateStore`:

```python
class StateStore(ABC):
    def create_experience(self, record: ExperienceRecord) -> ExperienceRecord: ...
    def get_experience(self, experience_id: UUID) -> ExperienceRecord | None: ...
    def list_recent_experiences(self, limit: int = 10) -> list[ExperienceRecord]: ...
```

Оркестрация высокого уровня — в `ExperienceService`:

```python
class ExperienceService:
    def create_experience(self, record: ExperienceRecord) -> ExperienceRecord: ...
    def get_experience(self, experience_id: UUID) -> ExperienceRecord | None: ...
    def add_reframing_note(self, experience_id: UUID, note: ReframingNote) -> ...: ...
    def search_by_session(self, session_id: UUID, limit: int = 10) -> list[ExperienceRecord]: ...
    def list_recent(self, limit: int = 10) -> list[ExperienceRecord]: ...
```

Все методы синхронные.

## Конфигурация

Experience Store использует тот же бэкенд `StateStore`, что и остальная система:

| `ATMAN_MEMORY_BACKEND` | Бэкенд |
|------------------------|--------|
| `inmemory` | `InMemoryStateStore` |
| `file` (по умолчанию) | `FileStateStore` — JSON-файлы + `key_moments.jsonl` |
| `postgres` | `PostgresStateStore` |

## Пример использования

```bash
# Запуск демо опыта
make demo-experience

# CLI
python -m atman.cli_experience
```

Программное использование:

```python
from uuid import UUID
from datetime import datetime, timezone

# Key moments добавляются во время сессии через SessionManager
session_manager.append_key_moment_input(session_id, KeyMomentInput(
    what_happened="Пользователь поделился давней frustration по поводу коммуникации в команде.",
    emotional_valence=-0.4,
    emotional_intensity=0.8,
    depth=EmotionalDepth.meaningful,
    why_it_matters="Длительная frustration указывает на проблему доверия.",
))

# После закрытия сессии — извлечь недавние опыты
experiences = experience_service.list_recent(limit=5)

# Позднее — проверить актуальную salience момента
moment = state_store.get_key_moment(moment_id)
current_salience = moment.calculate_current_salience(now=datetime.now(timezone.utc))
moment.mark_accessed()
```
