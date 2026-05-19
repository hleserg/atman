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

Опыты хранятся и извлекаются через `StateStore`:

```python
class StateStore(ABC):
    async def save_key_moment(self, moment: KeyMoment) -> None: ...
    async def get_key_moment(self, moment_id: str) -> KeyMoment | None: ...
    async def list_key_moments(self, session_id: str) -> list[KeyMoment]: ...
    async def save_session_experience(self, exp: SessionExperience) -> None: ...
    async def get_session_experience(self, session_id: str) -> SessionExperience | None: ...
```

Оркестрация высокого уровня — в `ExperienceService`:

```python
class ExperienceService:
    async def capture_key_moment(self, session_id: str, input: KeyMomentInput) -> KeyMoment: ...
    async def close_session(self, session_id: str) -> SessionExperience: ...
    async def retrieve_recent(self, limit: int) -> list[SessionExperience]: ...
```

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
# Во время сессии — записать key moment
moment_input = KeyMomentInput(
    description="Пользователь поделился давней frustration по поводу коммуникации в команде.",
    felt_sense=FeltSense(quality="тяжёлое, важное"),
    salience=0.85,
)
moment = await experience_service.capture_key_moment(session_id, moment_input)

# После закрытия сессии — извлечь опыт
exp = await experience_service.close_session(session_id)

# Позднее — проверить актуальную salience момента
current_salience = moment.calculate_current_salience(now=clock.now())
```
