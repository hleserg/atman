# Подробная карта реализованного кода Atman (RU)

Документ-обзор для разработчиков и аналитиков: что уже есть в репозитории, зачем каждый блок, основные функции, адаптеры, стыки и пробелы.  
Основан на коде в `src/atman/` и на `docs/architecture/SYSTEM_MAP-ru.md`. Если разделы расходятся с кодом, ниже отмечено явно.

---

## 1. Зачем Atman (в двух словах)

**Atman** — психологический слой поверх «сухих» фактов: отделяет **что произошло** (факты) от **как это пережили и что из этого следует для «я»** (опыт, идентичность, нарратив, рефлексия).

В коде: **модели** → **порты (интерфейсы)** → **сервисы (логика)** → **адаптеры (файлы, БД, HTTP)**.

---

## 2. Архитектурная проводка

- **Ядро** (`src/atman/core/`) — контракты и правила без Rich/HTTP «для UX».
- **Адаптеры** (`src/atman/adapters/`) — конкретные хранилища, моки, Ollama, PostgreSQL.
- **Точки входа** — CLI, TUI, Streamlit, `src/demo_*.py`; пользовательский вывод через **`atman.term`** (Rich).

**Замечание по документации:** в `SYSTEM_MAP-ru.md` §6 написано, что Session Manager «в очереди», но **`SessionManager` уже реализован** — ориентируйтесь на §1 и сценарии §3 карты.

---

## 3. Доменные модели (`core/models/`)

| Модуль | Суть простыми словами |
|--------|------------------------|
| `fact.py` | **Факт** — проверяемая запись («было X»), источник, теги, связи. Без эмоций и без «кто я». |
| `experience.py` | **Опыт первых рук**: сессия, ключевые моменты, окраска **в момент** (валентность, интенсивность, глубина), ценности, принципы. Оригинал не переписывается; сверху — **reframing notes**. Salience/importance, учёт доступа. |
| `identity.py` | **Идентичность**: самоописание, ценности, привычки, принципы, цели, открытые вопросы, baseline. **IdentitySnapshot** — снимок «каким я был». |
| `narrative.py` | **Самонарратив** (слои core/recent/threads) + **Eigenstate** — компактное состояние после сессии для старта следующей. |
| `session.py` | **Runtime сессии**: контекст, события, ввод ключевого момента, результат, сводка активных сессий. |
| `reflection.py` | **Рефлексия**: уровни micro/daily/deep, паттерны, события, здоровье (Йоды), DTO от модели. **ReflectionRecord** для персистенса (порт `reflection_store.py`). |
| `governance.py` | **Режимы** одобрения тяжёлых мутаций нарратива (auto / review / locked). |

---

## 4. Порты — «розетки» для реализаций

### 4.1. `FactualMemory` (`core/ports/memory_backend.py`)

Интерфейс факт-памяти: `add_fact`, `get_fact`, `search`, `invalidate_fact`, `list_invalidated`, `confirm_fact`, `decay_stale_facts`, `link`, `list_recent`.

**Зачем:** одна абстракция под память, файл или PostgreSQL.

### 4.2. `StateStore` (`core/ports/state_store.py`)

Единый порт состояния:

- **Опыт:** create, get, reframing note, `mark_accessed`, `search_experiences` (по сессии / ценностям / глубине / датам), `list_recent_experiences`.
- **Identity:** load/save, снимки, список снимков.
- **Narrative:** load/save (опционально `expected_updated_at` — оптимистичная блокировка), архив, список архивов.
- **Eigenstate:** save, `load_latest` (фильтр `identity_id`).

### 4.3. Рефлексия (`core/ports/reflection.py`)

- **ExperienceRepository**, **IdentityRepository**, **NarrativeRepository** — чтение/запись для рефлексии.
- **ReflectionModel** — генерация структурированных ответов (Pydantic DTO).
- **PatternStore**, **ReflectionEventStore**, **HealthAssessmentStore** — накопление артефактов рефлексии.
- **NarrativeWriteAuditPort** — аудит после коммита нарратива.
- **ReflectionEventPersistenceObserver** — сигнал, если событие рефлексии не сохранилось после других эффектов.

### 4.4. `ReflectionStore` (ABC) — `core/ports/reflection_store.py`

Порт для доменного **ReflectionRecord**: `add`, `get`, `list_by_session`, `list_recent`, `list_by_level`, `list_by_experience`. Реализация в репо: **InMemoryReflectionStore** (+ хелперы в `reflection_persistence_helper.py`).

### 4.5. `EmbeddingPort` (`core/ports/embedding.py`)

`embed`, `embed_batch`, `dimension`, `model_name`.

### 4.6. `MemoryUsageLog` (`core/ports/memory_usage_log.py`)

Учёт использования фактов/памяти для рефлексии и аналитики.

### 4.7. `MemoryMiddlewarePort` (`core/ports/memory_middleware.py`)

Протокол middleware: `prepare_context`, `note_fact_used`, `end_session`. **Конкретной реализации в ядре нет** — точка интеграции «живого агента» (MODEL-02).

### 4.8. `ClockPort` (`core/ports/clock.py`)

Время для воспроизводимости тестов и демо.

---

## 5. Сервисы (`core/services/`)

### 5.1. `ExperienceService`

- `create_experience`, `get_experience`, `add_reframing_note`, `mark_accessed`
- `calculate_current_salience`
- `search_by_session`, `search_by_values`, `search_by_depth`, `search_by_date_range`, `list_recent`

### 5.2. `IdentityService`

- `bootstrap_identity`, `get_identity`
- `update_self_description`, `add_core_value`, `add_habit`, `add_principle`, `add_goal`, `add_open_question`, `update_emotional_baseline`
- `create_snapshot`, `list_snapshots`

### 5.3. `NarrativeService`

- `create_narrative`, `get_narrative`
- `update_from_identity_and_eigenstate`
- `update_recent_layer`, `update_core_layer`, `add_thread`, `close_thread`
- `render_to_file`, `validate_narrative_file`

### 5.4. `SessionManager`

- `start_session` — identity, narrative, eigenstate, контекст
- `record_event` — сырой лог
- `record_key_moment` — значимый момент с эмоциональной окраской (или явная неполная окраска)
- `finish_session` — **SessionExperience** (детерминированный id от `session_id`), **Eigenstate**, дописывание recent narrative; проверки вроде `alignment_check=False` требуют заметок
- `get_active_session`, `list_active_sessions`

Ошибки: `SessionNotFoundError`, `SessionAlreadyFinishedError`, `TooManyActiveSessionsError` и др. (`core/exceptions.py`).

### 5.5. `MicroReflectionService` / `DailyReflectionService` / `DeepReflectionService`

- **Micro** — после сессии: опыт → модель → recent narrative (с конкуренцией), событие.
- **Daily** — за UTC-сутки: паттерны, reframing, события.
- **Deep** — за интервал: здоровье, глубокие паттерны, нарратив/identity, снимки с **`reflection_run_key`**.

### 5.6. `NarrativeRevisionService`

Мутации нарратива при рефлексии с governance и аудитом (recent/core, нити).

### 5.7. `PrincipleRevisionAdvisor`

`is_habit_not_principle`, `should_question_principle`, `suggest_principle_revision`.

### 5.8. `SessionWorkingMemory`

Кэш фактов/опыта в сессии, вытеснение по лимиту.

### 5.9. `PassiveMemoryInjector`

Пассивное всплытие: эмбеддинги + ассоциативное расширение по связям фактов; `surface_experiences`.

### 5.10. `EmotionalEcho`

Краткий эмоциональный фон из недавнего опыта.

### 5.11. `ConflictDetector`

Противоречия между активными фактами; `get_cognitive_tension`.

---

## 6. Адаптеры (`adapters/`)

### 6.1. Память фактов (`adapters/memory/`)

| Компонент | Порт | Назначение |
|-----------|------|------------|
| `InMemoryBackend` | `FactualMemory` | Тесты, без персистенса |
| `FileBackend` | `FactualMemory` | JSONL, блокировки |
| `PostgresFactualMemory` | `FactualMemory` | PostgreSQL + pgvector при `EmbeddingPort`, иначе ILIKE |
| `MockEmbeddingAdapter`, `BM25EmbeddingAdapter`, `OllamaEmbeddingAdapter` | `EmbeddingPort` | Мок / лексика / Ollama |
| `InMemoryUsageLog` | `MemoryUsageLog` | Учёт в памяти |

**Коннекторы сейчас:** `cli.py` → `FileBackend`; демо фактов — in-memory + file. PostgreSQL — отдельная ветка (`psycopg`, схема БД).

### 6.2. Хранилище состояния (`adapters/storage/`)

| Компонент | Порт | Назначение |
|-----------|------|------------|
| `InMemoryExperienceStore` | `StateStore` | Всё в процессе |
| `JsonlExperienceStore` | `StateStore` | Опыт JSONL |
| `FileStateStore` | `StateStore` | JSON-файлы: опыт + identity + narrative + eigenstate |
| Реализации в `in_memory_reflection_store.py` | Pattern/Event/Health сторы | Для доменной рефлексии |
| `InMemoryReflectionStore` (`in_memory_postgres_reflection_store.py`) | `core.ports.reflection_store.ReflectionStore` | In-memory + симуляция RLS |
| `reflection_persistence_helper.py` | использует порт `ReflectionStore` | `persist_micro/daily/deep_reflection` |

### 6.3. Модель рефлексии (`adapters/reflection/`)

- `MockReflectionModel` — без сети, детерминизм.
- `OllamaReflectionModel` — HTTP Ollama, JSON → DTO.
- `OllamaReflectionModelWithPersistence` — то же + запись в **PostgreSQL** через пакет `atman.reflection.store` (см. §7).
- `fixture_loader`, `prompts`, `exceptions`.

---

## 7. Два разных класса с именем ReflectionStore

В проекте **два независимых слоя**:

1. **`atman.core.ports.reflection_store.ReflectionStore`** (ABC) + **`ReflectionRecord`** — порт домена, in-memory адаптер, хелперы персистенса.
2. **`atman.reflection.store.ReflectionStore`** — конкретный **PostgreSQL**-класс для **`atman.reflection.models.ReflectionEvent`** (таблица `reflections`). Используется, например, в `OllamaReflectionModelWithPersistence`.

Имена совпадают, **модули разные** — при интеграции в прод важно не смешивать импорты.

---

## 8. Конфигурация (`config.py`)

- **`EmbeddingSettings`** — env с префиксом `EMBEDDING_*`: backend (`mock`/`ollama`), модель, размерность, хост Ollama, timeout.
- Глобальный **`settings`** с вложенным `embedding`.

---

## 9. Вспомогательное ядро

| Файл | Назначение |
|------|------------|
| `core/exceptions.py` | Ошибки домена и сессий |
| `core/clock_impl.py` | `SystemClock`, `FrozenClock` |
| `core/reflection_run_keys.py` | Детерминированные ключи прогонов |
| `core/narrative_write_audit.py` | Аудит коммитов нарратива |
| `core/reflection_event_audit.py` | Наблюдатели сохранения событий рефлексии |

---

## 10. Агентский слой Pydantic AI (`adapters/agent/`)

- **`AgentConfig`** — лимиты (tool calls, усечение нарратива).
- **`AtmanDeps`** — `SessionManager`, `IdentityService`, `ExperienceService`, `MicroReflectionService`, `StateStore`, `agent_id`, опционально `session_id`.
- **`tools.py`** — **`record_key_moment`** (валидация + `SessionManager`); **`log_experience`** — **заглушка** (опыт создаётся через `finish_session`).
- **`instructions.py`** — `build_instructions(deps)`: prompt из identity + narrative с усечением.

Это **кирпичи** для сборки агента (Pydantic AI и аналоги), не единый готовый «прод-агент» одной командой.

---

## 11. Презентация и демо

- **`term.py`** — Rich для CLI/демо.
- **`cli.py`**, **`cli_experience.py`**, **`cli_identity.py`**, **`cli_reflection.py`**
- **`tui/`** — Textual.
- **`web_dashboard/`** — Streamlit.
- **`src/demo_*.py`**, **`e2e/`** — воспроизводимые сценарии (см. `SYSTEM_MAP-ru.md` §3).

---

## 12. Eval (`src/atman/eval/` + `eval/migrations/`)

- **`atman.eval`** — optional extra **`atman[eval]`**; при импорте проверка зависимостей. Продакшен-код не должен импортировать eval (import-linter).
- Публичный API в `__init__.py` помечен как задел на будущее (runner, judge, …).
- **`eval/migrations/`** — Alembic под схему оценки/бенчмарков.

---

## 13. Пробелы и «ещё не воткнуто»

1. **`MemoryMiddlewarePort`** — только интерфейс, нет полной реализации в ядре.
2. **mem0 как внешний продукт** — в архитектурной доке как цель; в коде свой `FactualMemory`, не обязательно mem0.
3. **Graph DB / полнота vector search** — в отчётах/карте как незакрытые направления; pgvector есть у PostgreSQL-адаптера фактов.
4. **Два слоя персистенса рефлексий** (§7) — осознанное слияние при продвижении.
5. **`log_experience` в tools** — заглушка.
6. **Рост recent narrative без trim** — см. `SYSTEM_MAP-ru.md` §4.5.
7. **`atman.eval`** — каркас и миграции, не полный публичный runner в текущем `__init__.py`.

---

## 14. Сводка «модуль → зачем»

| Область | Зачем |
|---------|--------|
| Факты | Объективная опора, связи, поиск |
| StateStore + Experience | Переживания первых рук, неизменяемый оригинал + reframing |
| Identity + snapshots | Кто я, с историей |
| Narrative + Eigenstate | Рассказ о себе + состояние между сессиями |
| SessionManager | Запись опыта в момент и сбор артефактов сессии |
| Reflection L1–L3 | Смысл, паттерны, здоровье, долгие правки |
| Embeddings / PassiveMemory / Echo / Conflicts | Богаче и честнее контекст |
| CLI/TUI/Web/Demo | Проверка без прод-обвязки |
| Agent adapters | Подключение LLM к тем же сервисам |

---

*Последнее обновление содержимого: по состоянию репозитория на момент создания файла (анализ кодовой базы + SYSTEM_MAP-ru).*
