# Atman — Архитектура системы

## Обзор

Atman — психологический runtime-слой для AI-агентов. Он даёт агентам непрерывную идентичность, memory из первых рук и структурированную рефлексию. Это не замена LLM — это слой, который работает поверх него.

Нижний агент действует. Atman существует.

Система следует строгой слоистой архитектуре: **Core** (доменная логика) → **Ports** (интерфейсы) → **Adapters** (инфраструктура) → **Agent layer** (интеграция Pydantic AI).

## Основные принципы

- **Core не имеет внешних зависимостей.** Он никогда не импортирует LLM-клиенты или файловый I/O напрямую. Все внешние вызовы идут через порты (интерфейсы).
- **Порты определяют контракты.** Адаптеры реализуют их. Сервисы используют порты.
- **Clock инжектируется.** `datetime.now()` никогда не появляется в доменной логике — передаётся `ClockPort`.
- **Хранилище версионируется.** Все персистентные структуры несут версию схемы для совместимости.
- **Eval изолирован.** Продакшн-пользователи не платят за eval-инфраструктуру (см. ADR-001).

## Карта компонентов

### Доменные модели

Расположены в `src/atman/core/models/`.

| Файл | Классы |
|------|--------|
| `fact.py` | `FactRecord`, `Relation` — проверяемые факты и типизированные связи между сущностями |
| `experience.py` | `SessionExperience`, `KeyMoment`, `FeltSense`, `ContextHalo`, `ReframingNote`, `EmotionalDepth`, `ReframingNoteAppendResult` — пережитый опыт с decay значимости (`mark_accessed()`, `calculate_current_salience()`) и метаданными закрытия сессии |
| `identity.py` | `Identity`, `CoreValue`, `Habit`, `Principle`, `Goal`, `OpenQuestion`, `IdentitySnapshot`, `HelpfulnessLevel` — самопредставление агента |
| `narrative.py` | `NarrativeDocument`, `NarrativeLayer`, `NarrativeThread`, `Eigenstate`, `LayerType` — нарратив о себе с уровнями CORE / RECENT / THREADS |
| `session.py` | `SessionContext`, `SessionEvent`, `KeyMomentInput`, `SessionResult`, `ActiveSessionSummary`, `Session` — runtime и модели персистентности сессии |
| `reflection.py` | `ReflectionLevel`, `PatternCandidate`, `PatternStatus`, `PatternType`, `ReflectionEvent`, `HealthAssessment`, `JahodaCriterion`, `CriterionAssessment`, `ReflectionRecord` — трёхуровневая рефлексия с критериями психологического здоровья Яходы |

### Порты

Расположены в `src/atman/core/ports/`. Все — ABC или Protocol. Core зависит только от них, никогда от конкретных реализаций.

| Файл | Интерфейс |
|------|-----------|
| `memory_backend.py` | `FactualMemory` (ABC) — CRUD и поиск по фактам |
| `state_store.py` | `StateStore` — хранение опыта, идентичности, нарратива, eigenstate, key moments, сессий |
| `clock.py` | `ClockPort` (Protocol) — доменные часы; инжектируются везде, где был бы `datetime.now()` |
| `affect.py` | `AffectPort` (Protocol) — асинхронный affect hook, вызывается при каждом событии сессии |
| `reflection.py` | `ExperienceRepository`, `IdentityRepository`, `NarrativeRepository`, `ReflectionModel`, `PatternStore`, `ReflectionEventStore`, `HealthAssessmentStore` |
| `entity_registry.py` | `EntityRegistry` (ABC) — разрешение сущностей с уровнями кэша L1 / L2 / L3 |
| `embedding.py` | `EmbeddingPort` (Protocol) — интерфейс векторных эмбеддингов |
| `skill_manager.py` | `SkillManagerPort` (Protocol) — интерфейс жизненного цикла навыков |
| `maintenance_queue.py` | `MaintenanceQueue` (ABC) — очередь фоновых задач |
| `salience_decay.py` | `SalienceDecayService` (ABC) — decay значимости key moments |
| `memory_guardian.py` | `MemoryGuardian` (ABC) — проверки целостности памяти |
| `linguistic.py` | `LinguisticAnalyzer` (ABC) — NER и лингвистический анализ |
| `memory_reranker.py` | `MemoryReranker` (ABC) — повторное ранжирование результатов извлечения памяти |

### Сервисы

Расположены в `src/atman/core/services/`. Сервисы содержат доменную логику и зависят только от портов.

| Сервис | Ответственность |
|--------|-----------------|
| `ExperienceService` | Жизненный цикл опыта: захват, извлечение, закрытие сессий |
| `IdentityService` | Жизненный цикл идентичности, bootstrap, snapshot, применение рефлексии (`apply_self_change` / `revert_self_change`) |
| `NarrativeService` | Управление нарративными документами на уровнях CORE / RECENT / THREADS |
| `SessionManager` | Runtime сессии: `start_session`, `record_event` (с `AffectDetector` hook), `append_key_moment`, `finish_session` с eigenstate; опциональное восстановление после сбоя через журнал; опциональный `PostWriteScheduler` |
| `MicroReflectionService` | Обновление нарратива после сессии |
| `DailyReflectionService` | Обнаружение паттернов в последних опытах |
| `DeepReflectionService` | Глубокий анализ, карта связей сущностей, кандидаты на слияние |
| `PassiveMemoryInjector` | Извлекает релевантные факты и опыты через embedding similarity + BM25 |
| `ConflictDetector` | Обнаруживает противоречия между фактами |
| `InMemorySalienceDecayService` | In-process decay значимости key moments |
| `MaintenanceWorker` | Захватывает и обрабатывает maintenance-задачи из очереди |
| `AmbientMemoryService` | Entity-anchor параллельный RAG для ambient-контекста |

### Адаптеры

Расположены в `src/atman/adapters/`. Каждый адаптер реализует порт.

**Память (порт `FactualMemory`):**
- `InMemoryBackend` — эфемерный, для тестов
- `FileBackend` — JSONL append-only файл
- `PostgresFactualMemory` — PostgreSQL с полнотекстовым поиском

**Хранилище (порт `StateStore`):**
- `InMemoryStateStore` — эфемерный
- `FileStateStore` — JSON-файлы по типу записей + `key_moments.jsonl`
- `PostgresStateStore` — PostgreSQL

**Эмбеддинги (порт `EmbeddingPort`):**
- `OllamaEmbeddingAdapter` — локальный сервер Ollama (по умолчанию: bge-m3)
- `FlagEmbeddingAdapter` — BAAI/bge-m3 через библиотеку FlagEmbedding (1024d)
- `MockEmbeddingAdapter` — детерминированные нули для тестов
- `BM25EmbeddingAdapter` — разреженный BM25 поиск

**Лингвистика (порт `LinguisticAnalyzer`):**
- `GLiNERPlusMiniLMAdapter` — GLiNER распознавание сущностей + MiniLM
- `NoOpLinguisticAnalyzer` — pass-through, без анализа

**Реестр сущностей (порт `EntityRegistry`):**
- `InMemoryEntityRegistry`
- `PostgresEntityRegistry`

**Модель рефлексии (порт `ReflectionModel`):**
- `OpenAIReflectionModel` — любой OpenAI-совместимый API (llama-server, Ollama и т.д.)
- `MockReflectionModel` — детерминированные ответы для тестов

**Наблюдаемость:**
- `adapters/observability/sentry.py` — опциональная интеграция Sentry SDK. No-op при отсутствии `SENTRY_DSN`. Отслеживает ошибки, routine spans, ошибки трансляции, транзакции сессий, maintenance spans. Окружения: `dev`, `routine`, `ci`.

### Agent Layer

Расположен в `src/atman/adapters/agent/`.

| Компонент | Описание |
|-----------|----------|
| `AtmanRunner` / `AtmanTurn` | Pydantic AI agent runner с pre/post пайплайном, RAG-инъекцией, маршрутизацией триггеров навыков, полным жизненным циклом сессии |
| `AtmanDeps` | Контейнер для dependency injection, несущий все порты и сервисы |
| `factory.py` | Собирает полный стек из workspace path + `AgentConfig` |

Инструменты агента, доступные LLM:
- `record_key_moment` — сохранить key moment в ходе сессии
- `log_experience` — записать значимый опыт
- `restart_session` — корректно перезапустить текущую сессию
- `wait_session` — приостановить сессию и ждать
- `resolve_pending_review` — отметить ожидающий review рефлексии как решённый
- `request_reflection` — запустить цикл рефлексии по требованию

### Skills

Расположены в `src/atman/skills/`.

| Компонент | Описание |
|-----------|----------|
| `SkillManager` | Полный жизненный цикл: `invoke`, `mark_result`, `capture`, `process_session_skills`, `process_daily_skills`, `process_deep_skills` |
| `SkillManagerPort` | Канонический интерфейс (в `core/ports/`) |
| `InMemorySkillStore` | Эфемерное хранилище навыков |
| `PostgresSkillStore` | Персистентное хранилище навыков |

CLI: `atman-skills` — list, show, pin, unpin, invoke и другие команды.

## Поток данных

```
Ход пользователя/LLM
    │
    ▼
AtmanRunner (pre-pipeline)
    │  PassiveMemoryInjector → инжектировать релевантные факты + опыты в контекст
    │  AmbientMemoryService → entity-anchor RAG
    │
    ▼
LLM генерирует ответ
    │
    ▼
AtmanRunner (post-pipeline)
    │  SessionManager.record_event() → AffectPort hook
    │  SkillManagerPort → проверить триггеры навыков
    │  MaintenanceQueue → запланировать фоновые задачи
    │
    ▼
Завершение сессии
    │  SessionManager.finish_session()
    │  MicroReflectionService → обновление нарратива
    │  PostWriteScheduler → задачи daily/deep рефлексии
    │
    ▼
Персистентное хранилище (StateStore + FactualMemory)
```

## Внешние зависимости

| Зависимость | Роль | Обязательна |
|-------------|------|-------------|
| PostgreSQL | Factual memory, state, реестр сущностей (при `ATMAN_MEMORY_BACKEND=postgres`) | Нет — доступны file/inmemory бэкенды |
| llama-server или любой OpenAI-совместимый LLM | Модель рефлексии и LLM агента | Да |
| Ollama | Генерация эмбеддингов (bge-m3) | Нет — доступны FlagEmbedding или mock |
| Sentry | Отслеживание ошибок и мониторинг производительности | Нет — opt-in через `SENTRY_DSN` |
| Anthropic | Альтернативный LLM для рефлексии | Нет — opt-in через `ANTHROPIC_API_KEY` |

### Профили установки

| Профиль | Содержимое |
|---------|-----------|
| `pip install atman` | Только production runtime |
| `pip install "atman[eval]"` | Core + eval deps (Alembic, SQLAlchemy, PostgreSQL) |
| `pip install "atman[dev]"` | Core + dev/test deps |
| `pip install "atman[all]"` | Всё |

Модуль `eval/` изолирован за lazy import guard. Production-код никогда его не импортирует. См. ADR-001.
