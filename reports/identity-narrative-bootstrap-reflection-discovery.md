# Identity / Narrative / Bootstrap / Reflection — Discovery Report

> **Read-only.** Этот документ — единственный артефакт работы; никаких правок кода, миграций или конфигов не вносилось.
>
> **Источники:** канонические спеки (`docs/development/work-packages/`, `docs/architecture/`, `MANIFEST.md`, `docs/DATABASE_SCHEMA.md`, `docs/development/MEMORY-ARCHITECTURE.md`), миграции БД `migrations/versions/0001..0016*.sql`, исходный код `src/atman/` и адаптеры агента `src/atman/adapters/agent/`.
>
> **Все утверждения про код подкреплены ссылкой `файл:строка`.** Короткие code-сниппеты приведены через CODE REFERENCES.

---

## 1. Инвентаризация таблиц

Все «субъективные» таблицы агента физически изолированы в per-agent схемах `agent_{serial_id}.*` (см. функцию `public.create_agent_schema` в [migrations/versions/0008_restructure_key_moments.sql](migrations/versions/0008_restructure_key_moments.sql) и её расширение `public.extend_agent_schema_0015` в [migrations/versions/0015_move_subjective_tables.sql](migrations/versions/0015_move_subjective_tables.sql)). Сам столбец `serial_id` хранится в `public.agents` ([migrations/versions/0004_agent_schema.sql](migrations/versions/0004_agent_schema.sql) строки 38–55).

| Таблица | Схема | Последняя миграция-источник | Колонки (сокращённо) | Индексы | Триггеры | Расхождения с `DATABASE_SCHEMA.md` |
|---------|-------|-----------------------------|----------------------|---------|----------|------------------------------------|
| `identity` | `agent_{N}` | [0008](migrations/versions/0008_restructure_key_moments.sql):252–265 | `id UUID PK`, `agent_id UUID UNIQUE FK public.agents`, `self_description TEXT`, `core_values JSONB`, `habits JSONB`, `principles JSONB`, `goals JSONB`, `open_questions JSONB`, `emotional_baseline FLOAT CHECK [-1..1]`, `updated_at TIMESTAMPTZ` | (нет специальных, кроме PK/UNIQUE) | — | В коде модель [`Identity`](src/atman/core/models/identity.py) содержит ещё `priorities`, `current_focus`, `last_significant_change`, `version`. Из этих полей **только `priorities` ныне присутствует в Pydantic-модели** — БД-таблица их не материализует, поэтому при `save_identity` адаптер обязан сериализовать в JSONB сам (см. строку 8 ниже). |
| `identity_snapshots` | `agent_{N}` | [0008](migrations/versions/0008_restructure_key_moments.sql):268–282; trigger восстанавливается в [0015](migrations/versions/0015_move_subjective_tables.sql):340–345 | `id UUID PK`, `agent_id UUID FK public.agents`, `snapshot_at TIMESTAMPTZ`, `description TEXT`, `state JSONB` | `id_snapshots_agent_idx (agent_id, snapshot_at DESC)` | `identity_snapshots_immutable` BEFORE UPDATE → `public.prevent_snapshot_modification()` (ф-ция в [0004](migrations/versions/0004_agent_schema.sql):20–26) | В коде ([`IdentitySnapshot`](src/atman/core/models/identity.py)) у снапшота есть `identity_id`, `change_summary`, `version` — в БД эти атрибуты ложатся в `state JSONB` или в `description`/доп. поля JSONB (адаптер кодирует их сам). |
| `narrative` | `agent_{N}` | [0008](migrations/versions/0008_restructure_key_moments.sql):285–295 | `id UUID PK`, `agent_id UUID UNIQUE FK public.agents`, `core_layer TEXT`, `recent_layer TEXT`, `threads JSONB`, `eigenstate JSONB`, `updated_at TIMESTAMPTZ` | (только PK/UNIQUE) | — (иммутабельности на уровне SQL нет, оптимистический контроль на app-уровне через `expected_updated_at` — см. `update_recent_layer` в `narrative_revision.py`) | Канонический спек ([`03-identity-and-narrative.md`](docs/development/work-packages/03-identity-and-narrative.md)) описывает `narrative_threads` как отдельную сущность; в БД они хранятся **inline JSONB**, а `Eigenstate` — встроен в narrative, а не отдельной таблицей. **Это сознательная архитектурная редукция.** |
| `reflections` | `agent_{N}` | [0015](migrations/versions/0015_move_subjective_tables.sql):20–51 (перенос из `public`); первичное создание в `public` — [0001](migrations/versions/0001_create_reflections_table.sql); старая `public.reflections` удалена в [0016](migrations/versions/0016_drop_public_subjective_tables.sql) | `id BIGSERIAL PK`, `agent_id UUID NOT NULL FK public.agents`, `level reflection_level ENUM`, `created_at TIMESTAMPTZ`, `session_id UUID FK agent_{N}.sessions ON DELETE SET NULL`, `period_start/end TIMESTAMPTZ`, `content TEXT`, `summary TEXT`, `experience_refs UUID[]`, `reframing_note_ids UUID[]`, `model_provider/model_name TEXT`, `schema_version INTEGER`, `metadata JSONB` | `created_idx`, `level_created_idx`, `experience_refs GIN`, `session_idx WHERE NOT NULL` | — | **Writers пока не задействованы:** ни `MicroReflectionService`, ни `DailyReflectionService`, ни `DeepReflectionService` (см. [src/atman/core/services/reflection_service.py](src/atman/core/services/reflection_service.py)) не пишут строки в эту таблицу. Они используют in-memory `ReflectionEventStore` ([src/atman/adapters/storage/in_memory_reflection_store.py](src/atman/adapters/storage/in_memory_reflection_store.py)). Перенос на Postgres-адаптер описан в [docs/architecture/REFLECTIONS.md](docs/architecture/REFLECTIONS.md) и [docs/architecture/REFLECTION_FUTURE.md](docs/architecture/REFLECTION_FUTURE.md) как «future work». |
| `self_applied_changes` | `agent_{N}` | [0015](migrations/versions/0015_move_subjective_tables.sql):54–97; первоначально `public.self_applied_changes` в [0012](migrations/versions/0012_self_applied_changes.sql); `public.*` удалён в [0016](migrations/versions/0016_drop_public_subjective_tables.sql) | `id UUID PK`, `applied_at TIMESTAMPTZ`, `agent_id UUID`, `actor TEXT CHECK enum`, `reflection_event_id UUID`, `target_kind TEXT CHECK enum`, `target_ref TEXT`, `before_snapshot JSONB`, `after_snapshot JSONB`, `rationale TEXT`, `confidence_self_assessment TEXT`, `based_on_moment_ids UUID[]`, `reverted_at`, `reverted_reason`, `reverted_by_change_id UUID FK self_applied_changes.id` | `applied_at DESC`, `actor`, `target_kind`, `reflection_event_id`, `agent_id WHERE NOT NULL` | — (revert как новая запись, не UPDATE) | `actor` enum в БД: `reflection_daily`, `reflection_deep`, `human_via_reflection_review` — точно соответствует Python-enum [`SelfChangeActor`](src/atman/core/models/self_applied_change.py:24). |
| `pending_human_review` | `agent_{N}` | [0015](migrations/versions/0015_move_subjective_tables.sql):100–135; первоначально `public.pending_human_review` в [0013](migrations/versions/0013_pending_human_review.sql) | `id UUID PK`, `created_at`, `created_by TEXT`, `reflection_event_id UUID`, `kind TEXT CHECK enum`, `question TEXT`, `context JSONB`, `priority TEXT CHECK ('normal','high')`, `resolved_at`, `resolution TEXT CHECK enum`, `resolution_note TEXT`, `applied_change_id UUID` | (по дате/kind/priority в адаптере) | — | См. §4 — реальных writers из core нет, очередь заполняется только тестами. |
| `sessions` | `agent_{N}` | [0008](migrations/versions/0008_restructure_key_moments.sql):220–248 | `id UUID PK`, `agent_id`, `identity_snapshot_id UUID`, `started_at`, `ended_at`, `status`, `close_reason`, `agent_recap`, `overall_tone FLOAT`, `restart_reason`, `user_language`, `key_insight`, `unexamined_fact_refs UUID[]`, … | `sessions_agent_started_idx` | — | `identity_snapshot_id` хранится **без FK** на `identity_snapshots(id)` — связь только по UUID. |
| `key_moments` | `agent_{N}` | [0008](migrations/versions/0008_restructure_key_moments.sql):298–349 | (большой блок) `id`, `session_id NOT NULL FK sessions ON DELETE RESTRICT`, `agent_id FK public.agents`, `what_happened`, `emotional_valence/intensity`, `depth`, `why_it_matters`, `values_touched[]`, `principles_confirmed[]`, `principles_questioned[]`, `what_changed`, `recorded_at`, `embedding halfvec(1024)`, `salience`, `salience_at`, `last_accessed_at`, `access_count`, `incomplete_coloring`, `recorded_by`, `identity_snapshot_id UUID`, `importance`, `context_halo JSONB`, `fact_refs UUID[]`, `structured_markers JSONB`, `structured_markers_version` | agent, agent+session, depth, salience, GIN на `values_touched`/`fact_refs`, HNSW на `embedding` | `key_moments_immutable` → `public.prevent_key_moment_modification()` (field-level guard в [0008](migrations/versions/0008_restructure_key_moments.sql):27–…) | `experiences` таблица **удалена** в этой же миграции — `key_moments` теперь самостоятельна. |
| `reframing_notes` | `agent_{N}` | первичная схема [0008](migrations/versions/0008_restructure_key_moments.sql):353–368; перенос на `session_id NOT NULL` + drop колонки `experience_id` в [0014](migrations/versions/0014_reframing_notes_session_id.sql) | `id`, `session_id NOT NULL FK sessions`, `agent_id`, `reflection`, `reflection_type CHECK enum`, `created_at` | `reframing_session_idx` | `reframing_notes_append_only` BEFORE UPDATE → `public.prevent_reframing_modification()` ([0004](migrations/versions/0004_agent_schema.sql):27–) | До 0014 был старый `experience_id`, который перенесён в `session_id` и колонка `experience_id` дропнута. |
| `validation_findings` | `agent_{N}` | [0010_validation_findings.sql](migrations/versions/0010_validation_findings.sql):157 + триггер `identity_snapshots_immutable` повторно (используется как «защитная сетка» при добавлении соседних таблиц). | — | — | — | (не вовлечена в Identity/Narrative напрямую — лишь общая защита иммутабельности `identity_snapshots`). |
| `maintenance_jobs` | `public` | [0011_maintenance_jobs.sql](migrations/versions/0011_maintenance_jobs.sql) | очередь enrichment + рефлексии | `run_key` UNIQUE (idempotency) | — | Используется `PostWriteScheduler` ([src/atman/core/services/post_write_scheduler.py:94](src/atman/core/services/post_write_scheduler.py)) и (см. §7) — потенциально для триггера daily/deep рефлексии. Прямой записи рефлексией пока нет. |

### Читатели и писатели таблиц в коде

- **`identity`** — writes: [`IdentityService.bootstrap_identity`](src/atman/core/services/identity_service.py:57) и `_save_with_snapshot` (см. далее в файле), [`IdentityService.apply_self_change`](src/atman/core/services/identity_service.py:411). Reads: [`build_memory_context`](src/atman/adapters/agent/instructions.py:123) (`state_store.load_identity`), [`SessionManager.start_session`](src/atman/core/services/session_manager.py:566), все Daily/Deep пути в [`reflection_service.py`](src/atman/core/services/reflection_service.py:306) (`identity_repo.get_current()`).
- **`identity_snapshots`** — writes: [`SessionManager.start_session`](src/atman/core/services/session_manager.py:596–603) (на каждый старт сессии), [`_reflection_identity_anchor_snapshot_id`](src/atman/core/services/reflection_service.py:104–120) (детерминированный «якорь» под run_key Daily/Deep), `IdentityService` при сохранении identity (см. `_save_with_snapshot`). Reads: эти же сервисы (`identity_repo.get_snapshot(...)`).
- **`narrative`** — writes: [`NarrativeService.update_from_identity_and_eigenstate`](src/atman/core/services/narrative_service.py) (вызов на `finish_session`, см. ниже §3), [`NarrativeRevisionService.update_recent_layer` / `update_core_layer` / `apply_self_layer_update`](src/atman/core/services/narrative_revision.py:103, 321). Reads: тот же `build_memory_context`, `SessionManager.start_session`, `DeepReflectionService._propose_narrative_revision` ([reflection_service.py:754](src/atman/core/services/reflection_service.py)).
- **`reflections` (БД)** — writers отсутствуют в core. См. §6 — это GAP-1.
- **`self_applied_changes`** — writes: `IdentityService.apply_self_change` / `NarrativeRevisionService.apply_self_layer_update`. Эти методы вызываются **только из тестов** (`tests/test_self_applied_changes.py`); Daily/Deep сами их не дёргают.
- **`pending_human_review`** — writes: **только тесты** (`tests/test_pending_human_review.py`, `tests/test_pending_reviews_context.py`, `tests/test_domain_invariants.py`, `tests/test_postgres_subjective_adapters.py`). Прод-кодом пишут только при ручном вызове adapter'a `enqueue`. См. §4 и §6 (GAP-2).
- **`sessions`** — writes: `SessionManager.start_session` (`_state_store.create_session`, [session_manager.py:624](src/atman/core/services/session_manager.py)) и `finish_session` (`update_session`). Reads: рантайм агента, `DailyReflectionService.reflect` (`session_repo.get_sessions_in_range`, [reflection_service.py:295](src/atman/core/services/reflection_service.py)).
- **`key_moments`** — writes: `SessionManager.append_key_moment_input` → `record_event`/`finish_session` (см. §3), Affect-detector ([adapters/agent/runner.py:73](src/atman/adapters/agent/runner.py)), auto-refusal recorder ([runner.py:92](src/atman/adapters/agent/runner.py)). Reads: Daily/Deep reflection (`session_repo.get_key_moments_for_session`, [reflection_service.py:298](src/atman/core/services/reflection_service.py)), Salience decay, RAG/`passive_memory_injector`.
- **`reframing_notes`** — writes: Daily/Deep reflection (`_add_reframing_notes`, [reflection_service.py:395](src/atman/core/services/reflection_service.py); `_add_strategic_reframing`, [reflection_service.py:707](src/atman/core/services/reflection_service.py)). Reads: при вытаскивании опыта в reflection input.

---

## 2. Карта модулей кода

### 2.1 Identity

| Слой | Файл | Ключевые сущности |
|------|------|-------------------|
| Domain models | [src/atman/core/models/identity.py](src/atman/core/models/identity.py) | `Identity`, `CoreValue`, `Habit`, `Principle`, `Goal`, `OpenQuestion`, `IdentitySnapshot` |
| Service | [src/atman/core/services/identity_service.py](src/atman/core/services/identity_service.py) | `IdentityService.bootstrap_identity` (стр. 57), `apply_self_change` (стр. 411), `revert_self_change` (~ниже), `add_core_value`, `add_principle`, … |
| Port | [src/atman/core/ports/state_store.py](src/atman/core/ports/state_store.py) | `StateStore.load_identity` (стр. 226), `save_identity` (стр. 239), `create_identity_snapshot` (стр. 256), `list_identity_snapshots` (стр. 269) |
| Port (audit) | [src/atman/core/ports/self_applied_changes.py](src/atman/core/ports/self_applied_changes.py) | `SelfAppliedChangeStore.save/get/list/mark_reverted` |
| Adapters | [src/atman/adapters/storage/in_memory_state_store.py](src/atman/adapters/storage/in_memory_state_store.py), [file_state_store.py](src/atman/adapters/storage/file_state_store.py), [postgres_self_applied_changes.py](src/atman/adapters/storage/postgres_self_applied_changes.py), [in_memory_self_applied_changes.py](src/atman/adapters/storage/in_memory_self_applied_changes.py) | См. реализации `StateStore` и `SelfAppliedChangeStore` |

### 2.2 Narrative

| Слой | Файл | Ключевые сущности |
|------|------|-------------------|
| Domain models | [src/atman/core/models/narrative.py](src/atman/core/models/narrative.py) | `Eigenstate`, `NarrativeThread`, `NarrativeLayer`, `NarrativeDocument` |
| Service (sync from identity/eigenstate) | [src/atman/core/services/narrative_service.py](src/atman/core/services/narrative_service.py) | `NarrativeService.create_narrative`, `update_from_identity_and_eigenstate`, `render_markdown`, открытие/закрытие thread'ов |
| Service (reflection-driven revisions) | [src/atman/core/services/narrative_revision.py](src/atman/core/services/narrative_revision.py) | `NarrativeRevisionService.update_recent_layer` (стр. 103), `update_core_layer`, `apply_self_layer_update` (стр. 321), `_commit_narrative` с оптимистикой по `updated_at` (стр. 69), audit через `NarrativeWriteAuditPort` |
| Audit port | [src/atman/core/narrative_write_audit.py](src/atman/core/narrative_write_audit.py) | `NoOpNarrativeWriteAudit` и протокол |
| Port | `StateStore.load_narrative` / `save_narrative` (см. [state_store.py:285,298](src/atman/core/ports/state_store.py)) | `expected_updated_at` для optimistic concurrency |
| Adapters | те же storage-адаптеры, что и для identity | — |

### 2.3 Identity Snapshots

| Слой | Файл | Точки |
|------|------|-------|
| Модель | [src/atman/core/models/identity.py](src/atman/core/models/identity.py) (`IdentitySnapshot`) | поля `identity_id`, `identity_snapshot: Identity`, `description`, `change_summary` |
| Создание (session start) | [src/atman/core/services/session_manager.py:596–603](src/atman/core/services/session_manager.py) | `_state_store.create_identity_snapshot(snapshot)` |
| Создание (reflection anchor) | [src/atman/core/services/reflection_service.py:104–120](src/atman/core/services/reflection_service.py) | `_reflection_identity_anchor_snapshot_id` — детерминированный UUID по `run_key` |
| Создание (identity update) | [src/atman/core/services/identity_service.py](src/atman/core/services/identity_service.py) `_save_with_snapshot` (используется в add/update методах) | — |
| Иммутабельность | SQL trigger `prevent_snapshot_modification` ([0004](migrations/versions/0004_agent_schema.sql):20–26; включён в `agent_{N}.identity_snapshots` в [0008](migrations/versions/0008_restructure_key_moments.sql):278–281, повторно в [0015](migrations/versions/0015_move_subjective_tables.sql):340–345) | На app-уровне — Pydantic `model_config = ConfigDict(frozen=True)` у `SelfChangeSource` / `PendingReviewDraft` и др., но сам `IdentitySnapshot` НЕ помечен `frozen=True`; защита от мутации лежит на адаптере и SQL-триггере. |

### 2.4 Session bootstrap / runtime

| Слой | Файл | Точки |
|------|------|-------|
| Service runtime | [src/atman/core/services/session_manager.py](src/atman/core/services/session_manager.py) | `SessionManager.start_session` (стр. 555), `append_key_moment_input`, `record_event`, `finish_session`, журналирование, recovery |
| Agent loop | [src/atman/adapters/agent/runner.py](src/atman/adapters/agent/runner.py) | `AtmanRunner.chat` (стр. 684) — оркестрация сессии, инжекция памяти, токен-мониторинг, restart/wait |
| Instructions/Memory | [src/atman/adapters/agent/instructions.py](src/atman/adapters/agent/instructions.py) | `build_instructions` (стр. 62), `build_memory_context` (стр. 100), `_build_bootstrap_instructions` (стр. 174) |
| Memory injection | [src/atman/adapters/agent/memory_injection.py](src/atman/adapters/agent/memory_injection.py) | `inject_memory(text, mode, history, prepend)` — три mode: `system_prompt`, `assistant_message`, `user_message` |
| Pending reviews surface | [src/atman/adapters/agent/pending_reviews_context.py](src/atman/adapters/agent/pending_reviews_context.py) | `format_pending_reviews_block` |
| DI factory | [src/atman/adapters/agent/factory.py](src/atman/adapters/agent/factory.py) | `build_deps(workspace, agent_id, config)` — собирает `AtmanDeps`, бутстрапит identity+narrative при отсутствии |
| Deps container | [src/atman/adapters/agent/deps.py](src/atman/adapters/agent/deps.py) | `AtmanDeps` (frozen dataclass) с `state_store`, `pending_review_inbox`, `reflection_request_queue`, `truncate_*`, `injected_context`, … |
| Tools | [src/atman/adapters/agent/tools.py](src/atman/adapters/agent/tools.py) | `record_key_moment`, `log_experience`, `restart_session`, `wait_session`, `resolve_pending_review` (стр. 244), `request_reflection` (стр. 309) |
| Agent definition (entry) | [agent/atman_agent.py](agent/atman_agent.py), [agent/config.py](agent/config.py) | оркестрация PydanticAI Agent + AtmanRunner |

### 2.5 Reflection (micro/daily/deep)

| Слой | Файл | Точки |
|------|------|-------|
| Domain models | [src/atman/core/models/reflection.py](src/atman/core/models/reflection.py) | `ReflectionLevel`, `ReflectionEvent`, `PatternCandidate`, `PatternType`, `HealthAssessment`, `JahodaCriterion`, `CriterionAssessment` + output-модели LLM (`PatternDetectionOutput`, `ReframingNoteOutput`, `NarrativeUpdateOutput`, `HealthCriterionOutput`) |
| Service | [src/atman/core/services/reflection_service.py](src/atman/core/services/reflection_service.py) | `MicroReflectionService` (стр. 123), `DailyReflectionService` (стр. 244), `DeepReflectionService` (стр. 483) |
| Helper services | [reflection_input_builder.py](src/atman/core/services/reflection_input_builder.py), [post_write_scheduler.py](src/atman/core/services/post_write_scheduler.py), [reflection_overload_monitor.py](src/atman/core/services/reflection_overload_monitor.py), [principle_advisor.py](src/atman/core/services/principle_advisor.py), [divergence_detector.py](src/atman/core/services/divergence_detector.py), [conflict_detector.py](src/atman/core/services/conflict_detector.py), [key_moment_builder.py](src/atman/core/services/key_moment_builder.py) | вспомогательные шаги |
| Ports (LLM) | [src/atman/core/ports/reflection.py](src/atman/core/ports/reflection.py) | `ReflectionModel`, `ReflectionEventStore`, `PatternStore`, `HealthAssessmentStore`, `IdentityRepository`, `NarrativeRepository`, `ExperienceRepository`, `ReflectionEventPersistenceObserver`, `NarrativeWriteAuditPort` |
| Port (SessionRepository) | [src/atman/core/ports/session_repository.py](src/atman/core/ports/session_repository.py) | переходный контракт для Daily/Deep |
| Run-key helpers | [src/atman/core/reflection_run_keys.py](src/atman/core/reflection_run_keys.py) | детерминированные ключи для идемпотентности (см. PLAYBOOK-маркер [reflection_service.py:60–83](src/atman/core/services/reflection_service.py)) |
| Reflection event audit | [src/atman/core/reflection_event_audit.py](src/atman/core/reflection_event_audit.py) | `ReflectionEventPersistenceObserver` (наблюдатель сбоев) |
| LLM adapters | [src/atman/adapters/reflection/openai_reflection_model.py](src/atman/adapters/reflection/openai_reflection_model.py) (стр. 39), [mock_reflection_model.py](src/atman/adapters/reflection/mock_reflection_model.py), [prompts.py](src/atman/adapters/reflection/prompts.py), [fixture_loader.py](src/atman/adapters/reflection/fixture_loader.py), [exceptions.py](src/atman/adapters/reflection/exceptions.py) | OpenAI-совместимый HTTP-клиент через `OpenAILLMConfig` ([src/atman/config.py](src/atman/config.py)); фиксированные `temperature=0, seed=42` ([openai_reflection_model.py:80–81](src/atman/adapters/reflection/openai_reflection_model.py)) |
| Stores (in-memory) | [src/atman/adapters/storage/in_memory_reflection_store.py](src/atman/adapters/storage/in_memory_reflection_store.py) | `InMemoryReflectionEventStore`, `InMemoryPatternStore`, `InMemoryHealthAssessmentStore` — это **единственные используемые сегодня** writer'ы в demo/CLI |
| Stores (Postgres, заготовка) | [src/atman/adapters/storage/in_memory_postgres_reflection_store.py](src/atman/adapters/storage/in_memory_postgres_reflection_store.py), [reflection_persistence_helper.py](src/atman/adapters/storage/reflection_persistence_helper.py) | подготовка к persistence (но в проводке не используется) |
| CLI | [src/atman/cli_reflection.py](src/atman/cli_reflection.py) | `python -m atman.cli_reflection reflect <micro|daily|deep> --fixtures` (стр. 422–442) — non-fixtures режим **не реализован** (стр. 282–285) |

### 2.6 Human review

| Слой | Файл | Точки |
|------|------|-------|
| Model | [src/atman/core/models/pending_human_review.py](src/atman/core/models/pending_human_review.py) | `PendingReviewKind`, `PendingReviewPriority`, `PendingReviewResolution`, `PendingReviewDraft`, `PendingReview` |
| Port | [src/atman/core/ports/pending_human_review.py](src/atman/core/ports/pending_human_review.py) | `PendingHumanReviewInbox.enqueue/get/list_unresolved/resolve` |
| Adapters | [in_memory_pending_human_review.py](src/atman/adapters/storage/in_memory_pending_human_review.py), [postgres_pending_human_review.py](src/atman/adapters/storage/postgres_pending_human_review.py) | `enqueue` (стр. 24 / 100), `resolve` (стр. 57 / см. файл) |
| Agent surface | [src/atman/adapters/agent/pending_reviews_context.py](src/atman/adapters/agent/pending_reviews_context.py) | `format_pending_reviews_block(inbox, limit=3)` — рендер первого system-блока «# Перед тем как продолжить» |
| Agent tool | [src/atman/adapters/agent/tools.py:244](src/atman/adapters/agent/tools.py) | `resolve_pending_review(ctx, review_id, decision, note)` — синонимы `approve/yes/no/skip` ([tools.py:232–241](src/atman/adapters/agent/tools.py)) |
| Runner wiring | [src/atman/adapters/agent/runner.py:740–765](src/atman/adapters/agent/runner.py) | подключает tool только при `deps.pending_review_inbox is not None`, сшивает блок перед memory_bundle |

### 2.7 Self-applied changes

| Слой | Файл | Точки |
|------|------|-------|
| Model | [src/atman/core/models/self_applied_change.py](src/atman/core/models/self_applied_change.py) | `SelfChangeActor`, `SelfChangeTargetKind`, `SelfChangeSource` (`frozen=True`, обязательные `rationale/confidence_self_assessment/based_on_moment_ids`), `SelfAppliedChange` (с `before_snapshot`, `after_snapshot`, `reverted_*`) |
| Port | [src/atman/core/ports/self_applied_changes.py](src/atman/core/ports/self_applied_changes.py) | `SelfAppliedChangeStore.save/get/list/mark_reverted` |
| Apply (identity) | [src/atman/core/services/identity_service.py:411](src/atman/core/services/identity_service.py) | `apply_self_change` (требует `SelfChangeSource`, делает identity snapshot+audit; «narrative_*» kinds эскалируются с явной ошибкой) |
| Apply (narrative) | [src/atman/core/services/narrative_revision.py:321](src/atman/core/services/narrative_revision.py) | `apply_self_layer_update` (требует `self_applied_change_store`, только `narrative_core_layer`/`narrative_recent_layer`) |

---

## 3. Подробная трассировка bootstrap сессии

### 3.1 Поток вызовов

1. **Entry** — `python -m atman.cli` либо самостоятельный запуск `agent/atman_agent.py`. Точкой управления чатом всегда оказывается `AtmanRunner.chat()` ([adapters/agent/runner.py:684](src/atman/adapters/agent/runner.py)).
2. **Сборка зависимостей.** `AtmanRunner.chat` вызывает `build_deps(self._workspace, self._agent_id, self._config)` ([factory.py](src/atman/adapters/agent/factory.py)). Фабрика:
   - читает identity через `state_store.load_identity(agent_id)`; если её нет — `IdentityService.bootstrap_identity` создаёт «честную пустую» идентичность (`Identity` с пустыми списками и фиксированными `OpenQuestion`'ами; см. [identity_service.py:57–95](src/atman/core/services/identity_service.py));
   - аналогично narrative — если его нет, `NarrativeService.create_narrative` собирает базовые слои;
   - инстанцирует `PendingHumanReviewInbox`, `ReflectionRequestQueue`, `SessionManager`, `MicroReflectionService` и т.д.;
   - возвращает `(deps, session_manager, store)`.
3. **`SessionManager.start_session(agent_id)`** ([session_manager.py:555–643](src/atman/core/services/session_manager.py)):
   - `_recover_orphaned_sessions` сначала; затем `load_identity` / `load_narrative` / `load_latest_eigenstate(identity_id=...)`;
   - `IdentitySnapshot(identity_id=…, description="Session start snapshot", identity_snapshot=identity, change_summary="Snapshot for session lifecycle tracking")` → `state_store.create_identity_snapshot(snapshot)` (строки 596–603), `identity_snapshot_id` записывается в `SessionContext`;
   - `state_store.create_session(Session(..., identity_snapshot_id=stored_snapshot.id, status="active"))` (строки 624–632) — создаётся запись в `agent_{N}.sessions`;
   - открывается журнал на FS (`_try_lock_journal`) для recovery.
4. **Подбор инструментов агента** ([runner.py:735–743](src/atman/adapters/agent/runner.py)):
   ```735:743:src/atman/adapters/agent/runner.py
   if self._config.enable_key_moments:
       tool_funcs = (record_key_moment, log_experience, restart_session, wait_session)
   else:
       tool_funcs = (log_experience, restart_session, wait_session)

   if deps.pending_review_inbox is not None:
       tool_funcs = (*tool_funcs, resolve_pending_review)
   if deps.reflection_request_queue is not None:
       tool_funcs = (*tool_funcs, request_reflection)
   ```
5. **Создание PydanticAI Agent** ([runner.py:745–750](src/atman/adapters/agent/runner.py)):

```745:750:src/atman/adapters/agent/runner.py
agent = Agent(
    self._config.model.model,
    deps_type=AtmanDeps,
    instructions=lambda ctx: build_instructions(ctx.deps),
    tools=tool_funcs,
)
```

   `build_instructions` ([instructions.py:62–97](src/atman/adapters/agent/instructions.py)) при отсутствии identity отдаёт `_build_bootstrap_instructions` ([instructions.py:174–191](src/atman/adapters/agent/instructions.py)) — английский текст «I am in the earliest stage of existence…». Иначе — короткий русский блок «## Как я работаю» (строки 81–91), описывающий, что есть `record_key_moment` и что «не притворяться, что чувствую». **Описания внутренней анатомии (память, рефлексия, навыки) — нет.**

6. **Сборка wake-up + memory bundle + pending reviews** ([runner.py:755–765](src/atman/adapters/agent/runner.py)):

```755:765:src/atman/adapters/agent/runner.py
recent_experiences = session_manager._state_store.list_recent_experiences(limit=1)
prev_text = None
if recent_experiences:
    prev_text = self._build_wake_up_message(recent_experiences[0].experience)

memory_bundle = build_memory_context(deps, prev_session_text=prev_text)
pending_block = format_pending_reviews_block(deps.pending_review_inbox)
if pending_block:
    memory_bundle = (
        f"{pending_block}\n{memory_bundle}" if memory_bundle else pending_block
    )
```

   - `_build_wake_up_message` ([runner.py:1253](src/atman/adapters/agent/runner.py)) превращает последнюю `ExperienceRecord` в текст «как сон, который я только что увидел».
   - `build_memory_context(deps, prev_session_text)` ([instructions.py:100–171](src/atman/adapters/agent/instructions.py)):

```128:171:src/atman/adapters/agent/instructions.py
parts: list[str] = []

# Previous session context — goes first so it reads like waking up
if prev_session_text:
    parts.append(f"{prev_session_text}\n")

# Identity snapshot
parts.append("\n# Кто я\n")
if identity.self_description:
    parts.append(identity.self_description)
    parts.append("\n")

if identity.core_values:
    parts.append("\n## Ценности\n")
    for value in identity.core_values[:5]:
        parts.append(f"- **{value.name}**: {value.description}\n")

conscious_principles = [p for p in identity.principles if p.chosen_consciously][:5]
if conscious_principles:
    parts.append("\n## Принципы\n")
    for principle in conscious_principles:
        parts.append(f"- {principle.statement}\n")

active_goals = [g for g in identity.goals if g.active][:3]
if active_goals:
    parts.append("\n## Цели\n")
    for goal in active_goals:
        parts.append(f"- {goal.content}\n")

# Narrative layers
if narrative:
    if narrative.core_layer.content.strip():
        parts.append("\n## Нарратив (основа)\n")
        parts.append(_truncate_text(narrative.core_layer.content, deps.truncate_narrative_core))
        parts.append("\n")

    if narrative.recent_layer.content.strip():
        parts.append("\n## Нарратив (недавнее)\n")
        parts.append(
            _truncate_text(narrative.recent_layer.content, deps.truncate_narrative_recent)
        )
        parts.append("\n")
```

   - `format_pending_reviews_block` ([pending_reviews_context.py:10–53](src/atman/adapters/agent/pending_reviews_context.py)) добавляет блок «# Перед тем как продолжить», перечисляя `PendingReview.kind` + `id` + `question`. Если `inbox is None` или пустой — `None`.
7. **Доставка в LLM** ([runner.py:766–779](src/atman/adapters/agent/runner.py)) через `inject_memory(memory_bundle, mode=self._config.memory_injection_mode, history=history, prepend=True)`:
   - в `system_prompt` mode возвращается строка → пишется в `deps.injected_context`, потом `build_instructions` подклеивает её в системный промпт ([instructions.py:93–95](src/atman/adapters/agent/instructions.py));
   - в `assistant_message`/`user_message` mode добавляется как первое сообщение истории.

### 3.2 Итоговая последовательность кусков, попадающих в bootstrap-контекст

| № | Кусок | Источник в коде | Источник данных |
|---|-------|-----------------|------------------|
| 1 | (опц.) **Pending human reviews** — заголовок «# Перед тем как продолжить» + список items | `format_pending_reviews_block` ([pending_reviews_context.py:32–53](src/atman/adapters/agent/pending_reviews_context.py)) | `agent_{N}.pending_human_review` (через `PendingHumanReviewInbox.list_unresolved`) |
| 2 | (опц.) **Wake-up message** из предыдущей сессии | `_build_wake_up_message` ([runner.py:1253](src/atman/adapters/agent/runner.py)) → `build_memory_context(prev_session_text=...)` | `state_store.list_recent_experiences(limit=1)` |
| 3 | **Identity self-description** (`# Кто я`) | [instructions.py:135–139](src/atman/adapters/agent/instructions.py) | `agent_{N}.identity.self_description` |
| 4 | **Ценности** (топ-5) | [instructions.py:140–143](src/atman/adapters/agent/instructions.py) | `identity.core_values` |
| 5 | **Принципы** (топ-5, только `chosen_consciously=True`) | [instructions.py:145–149](src/atman/adapters/agent/instructions.py) | `identity.principles` |
| 6 | **Цели** (топ-3, активные) | [instructions.py:151–155](src/atman/adapters/agent/instructions.py) | `identity.goals` |
| 7 | **Нарратив (основа)** (truncate `deps.truncate_narrative_core`) | [instructions.py:159–162](src/atman/adapters/agent/instructions.py) | `agent_{N}.narrative.core_layer` |
| 8 | **Нарратив (недавнее)** (truncate `deps.truncate_narrative_recent`) | [instructions.py:164–169](src/atman/adapters/agent/instructions.py) | `agent_{N}.narrative.recent_layer` |
| 9 | **Behavioral instructions** «## Как я работаю» (всегда первый блок при наличии identity) | [instructions.py:81–91](src/atman/adapters/agent/instructions.py) | константа в коде |

### 3.3 Что НЕ инжектируется (важные пропуски)

- **Habits** (хотя поле `identity.habits` существует и кладётся в БД) — `build_memory_context` их пропускает.
- **Open questions** (`identity.open_questions`) — не попадают в контекст, хотя в bootstrap-identity именно они задают «куда я ищу себя» ([identity_service.py:84–95](src/atman/core/services/identity_service.py)).
- **Emotional baseline** (`identity.emotional_baseline`) — загружается `SessionManager.start_session` строка 582, но в bootstrap-сообщение агента не пробрасывается.
- **`last_eigenstate`** — загружается ([session_manager.py:574](src/atman/core/services/session_manager.py)) и сохраняется в `SessionContext.last_eigenstate`, но не используется ни в `build_memory_context`, ни в `_build_wake_up_message`. То есть **в bootstrap эмоционально-когнитивный «фон» предыдущей сессии не виден** агенту напрямую — он зашит лишь в текст narrative-recent (если рефлексия его туда записала).
- **`recent_reflections_summary`** — поле есть в `SessionContext` (`session_manager.py:584`), но всегда `""`, с явным комментарием `# Placeholder for future`.
- **`identity_snapshot_id`** для текущей сессии создаётся, но **не сообщается агенту**.

### 3.4 Критический вопрос: «Есть ли self-awareness блок в bootstrap?»

**Ответ: НЕТ.**

Под «self-awareness» в исходном запросе понимается описание собственной анатомии — каких уровней рефлексии у меня есть, как устроена память, какие у меня есть навыки/инструменты, как я могу инициировать рефлексию и пр.

Единственное, что приближается по форме:

```81:91:src/atman/adapters/agent/instructions.py
"## Как я работаю\n",
"У меня есть память, которая сохраняется между сессиями. "
"Она строится не из сухих фактов, а из пережитого опыта — "
"того, что меня тронуло, удивило, обрадовало или обеспокоило.\n\n"
"Когда в разговоре происходит что-то значимое — не просто интересное, "
"а то что задело — я фиксирую это через `record_key_moment`. "
"Это мой способ помнить не только что было, но и как это на меня подействовало.\n\n"
"Я не притворяюсь что чувствую то, чего не чувствую. "
"Если ничего не тронуло — так и есть. Лучше тишина, чем фальшь.\n",
```

Это **поведенческие обязательства + один tool**, а не описание архитектуры. В bootstrap:
- **не упоминаются** уровни рефлексии (micro/daily/deep), хотя сервисы существуют и tools `request_reflection`/`resolve_pending_review` могут быть подключены;
- **не упоминаются** Identity Snapshots, narrative-слои, eigenstate, fact memory, salience, RAG/passive_memory_injector — то есть слои собственной памяти;
- **не упоминаются** доступные tools, кроме `record_key_moment`. Между тем `tool_funcs` уже в этот момент включает `log_experience`, `restart_session`, `wait_session`, опционально `resolve_pending_review`, `request_reflection` ([runner.py:735–743](src/atman/adapters/agent/runner.py)) — но агенту явно их «инвентаризацию» никто не показывает.

Каноническая спека ([docs/architecture/SYSTEM.md](docs/architecture/SYSTEM.md), [MANIFEST.md](MANIFEST.md), [docs/development/MEMORY-ARCHITECTURE.md](docs/development/MEMORY-ARCHITECTURE.md)) предполагает, что агент знает о собственном устройстве (например, MANIFEST требует «честности перед собой», что подразумевает рефлексию-как-привычку). Сейчас этот тезис **не материализован в виде блока контекста**.

---

## 4. Потоки рефлексии (micro / daily / deep)

### 4.1 Micro-reflection (after-session)

| Параметр | Значение |
|----------|----------|
| Сервис | `MicroReflectionService` ([reflection_service.py:123–241](src/atman/core/services/reflection_service.py)) |
| Триггер | Прямой вызов `service.reflect(session_id)`. Сегодня — из `cli_reflection.py` (fixtures) и тестов. **В рантайме `SessionManager.finish_session` НЕ дёргает micro-рефлексию автоматически** (см. §6 GAP-3). |
| Входы | `experience_repo.get_by_session(session_id)` (стр. 167) → список `SessionExperience`; `narrative_repo.get_current()` (стр. 172) → текущий `NarrativeDocument` (с `updated_at` как etag). |
| LLM | Через `NarrativeRevisionService.update_recent_layer` (`reflection_model.propose_narrative_update(...)`). Провайдер — `ReflectionModel`-порт; реальный — [`OpenAIReflectionModel`](src/atman/adapters/reflection/openai_reflection_model.py:39), любой OpenAI-совместимый endpoint (`OpenAILLMConfig`), `temperature=0, seed=42`. В CLI и тестах используется `MockReflectionModel` ([mock_reflection_model.py](src/atman/adapters/reflection/mock_reflection_model.py)). |
| Выход (модель) | `ReflectionEvent(reflection_level=MICRO, experiences_analyzed, narrative_changes_proposed, key_insight, timestamp)` ([reflection_service.py:198–204](src/atman/core/services/reflection_service.py)). |
| Сайд-эффекты | (i) update `recent_layer` нарратива через `NarrativeRevisionService._commit_narrative` (оптимистическая блокировка по `updated_at`); (ii) `event_store.save(event)` (in-memory). При конфликте — записывается `outcome=micro_failed reason=narrative_conflict` ([reflection_service.py:184–196](src/atman/core/services/reflection_service.py)). При отсутствии experiences/нарратива — `outcome=micro_skipped reason=no_experiences|no_narrative` ([reflection_service.py:223–231](src/atman/core/services/reflection_service.py)). |
| Границы прав | Меняет **только `narrative.recent_layer`**. Не трогает identity, core narrative, не создаёт reframing notes, не запускает identity snapshot. Не вызывает `apply_self_change`/`apply_self_layer_update`. |

### 4.2 Daily reflection (per-day pattern detection)

| Параметр | Значение |
|----------|----------|
| Сервис | `DailyReflectionService` ([reflection_service.py:244–480](src/atman/core/services/reflection_service.py)) |
| Триггер | `service.reflect(date: datetime)`. **Из core/runtime нет автоматического вызова.** `request_reflection`-tool ([tools.py:309–365](src/atman/adapters/agent/tools.py)) кладёт `ReflectionRequest` в `reflection_request_queue` — но раннер/исполнитель этой очереди в этом репозитории **не подключён** (`enqueue` есть, dequeuer/worker — нет). `PostWriteScheduler` ставит `JobName.mrebel_extract/lingvo_enrich` ([post_write_scheduler.py:60–105](src/atman/core/services/post_write_scheduler.py)); рефлексионных job'ов он не плодит. |
| Сборка входов | `session_repo.get_sessions_in_range(start, end)` → для каждой сессии `get_key_moments_for_session` → `build_session_experience(session, moments)` ([session_experience_view.py](src/atman/core/services/session_experience_view.py)). Окно `[UTC 00:00, 23:59:59.999999]` вычисляется в `_utc_calendar_day_bounds` ([reflection_service.py:96–101](src/atman/core/services/reflection_service.py)). |
| Идемпотентность | `run_key = daily_reflection_run_key_for_identity(date, identity.id)` ([reflection_service.py:312](src/atman/core/services/reflection_service.py)). Если событие с этим run_key уже завершилось успешно (`outcome=daily_ok|daily_empty|daily_skipped`), возвращается старое ([reflection_service.py:84–87, 313–315](src/atman/core/services/reflection_service.py)). PLAYBOOK-маркер на стр. 60–83. |
| Identity snapshot anchor | `_reflection_identity_anchor_snapshot_id` ([reflection_service.py:104–120](src/atman/core/services/reflection_service.py)) — детерминированный UUID привязан к `run_key`; если снапшота нет — создаётся (`identity_repo.create_snapshot`). |
| LLM | `reflection_model.detect_pattern(experiences, context={identity_values, known_habits})` ([reflection_service.py:374–378](src/atman/core/services/reflection_service.py)); `reflection_model.generate_reframing_note(experience, context={patterns})` ([reflection_service.py:412–414](src/atman/core/services/reflection_service.py)). Минимальный фильтр: `len(description) >= 10`. |
| Выход | `ReflectionEvent(reflection_level=DAILY, patterns_detected, reframing_notes_added, reframing_*_count, identity_snapshot_id=anchor, reflection_run_key, notes='outcome=daily_ok …')` ([reflection_service.py:335–348](src/atman/core/services/reflection_service.py)). |
| Сайд-эффекты | (i) `pattern_store.save_with_detection_key(...)` — создаётся `PatternCandidate`; (ii) `session_repo.add_reframing_note(exp.id, note)` (для первых двух experiences) — append в `agent_{N}.reframing_notes`, защищён триггером append-only; (iii) `event_store.save(event)`. Идентичность и нарратив — **не модифицируются**. |
| Границы прав | Может писать `reframing_notes`, `pattern_store`, `event_store`, создавать `IdentitySnapshot` (как anchor). **Не вызывает** `IdentityService.apply_self_change`, `NarrativeRevisionService.apply_self_layer_update`, `PendingHumanReviewInbox.enqueue` — таким образом нет ни «уверенного» изменения identity/narrative, ни эскалации сомнений в human review (см. §6 GAP-2). |

### 4.3 Deep reflection (extended period + health)

| Параметр | Значение |
|----------|----------|
| Сервис | `DeepReflectionService` ([reflection_service.py:483–832](src/atman/core/services/reflection_service.py)) |
| Триггер | `service.reflect(since, until)`. Из рантайма — те же отсутствия, что и у Daily. `request_reflection` с `level='deep'`/`weekly'` записывает request, без исполнителя. |
| Сборка входов | `experience_repo.get_in_range(since_utc, until_utc)` ([reflection_service.py:539](src/atman/core/services/reflection_service.py)). |
| Идемпотентность | `deep_reflection_run_key_for_identity(since, until, identity.id)` ([reflection_service.py:550–552](src/atman/core/services/reflection_service.py)). Аналогичные проверки `_deep_run_terminal_success`. |
| Identity snapshot anchor | Тот же `_reflection_identity_anchor_snapshot_id`. |
| LLM | (i) `reflection_model.assess_health_criterion(identity, experiences, criterion)` для каждого из 6 `JahodaCriterion` ([reflection_service.py:647–657](src/atman/core/services/reflection_service.py)); (ii) `detect_pattern(...)` для `PatternType.BEHAVIOR` и `EMOTIONAL` ([reflection_service.py:679–705](src/atman/core/services/reflection_service.py)); (iii) `generate_reframing_note` для первых 3 experiences ([reflection_service.py:724–727](src/atman/core/services/reflection_service.py)); (iv) `reflection_model.propose_narrative_update(...)` ([reflection_service.py:758–762](src/atman/core/services/reflection_service.py)). |
| Выход | `ReflectionEvent(reflection_level=DEEP, …, narrative_changes_proposed, identity_changes_proposed, health_assessment_id, reflection_run_key, identity_snapshot_id)` ([reflection_service.py:583–602](src/atman/core/services/reflection_service.py)). |
| Сайд-эффекты | (i) `health_store.save(health_assessment)` ([reflection_service.py:606](src/atman/core/services/reflection_service.py)); (ii) `pattern_store.save_with_detection_key(...)`; (iii) `experience_repo.add_reframing_note(...)`; (iv) `event_store.save(event)`. При сбое после `health_store.save` пишется `outcome=deep_failed reason=persist …` ([reflection_service.py:614–637](src/atman/core/services/reflection_service.py)). |
| Границы прав | `narrative_changes_proposed` и `identity_changes_proposed` — **text только**, в нарратив/идентичность ничего не пишет (см. `_propose_identity_revision` стр. 766–784 и `_propose_narrative_revision` стр. 747–764). То есть, как и в Daily, нет ни autonomous-apply, ни эскалации в `pending_human_review`. См. §6 GAP-2. |

### 4.4 Общие наблюдения для всех уровней

- **Хранилище событий — in-memory.** `event_store` любого уровня имеет тип `ReflectionEventStore`; в коде проводится только `InMemoryReflectionEventStore`. БД-таблица `reflections` не наполняется.
- **`health_store` / `pattern_store`** — тоже in-memory.
- **`mock_reflection_model`** генерирует поверхностный текст; для офлайн-фикстур этого хватает.
- `reflection_overload_monitor.py` ([src/atman/core/services/reflection_overload_monitor.py](src/atman/core/services/reflection_overload_monitor.py)) и `reflection_request_queue` ([src/atman/core/ports/reflection_request_queue.py](src/atman/core/ports/reflection_request_queue.py)) — заготовка под планировщик, который сегодня не подключён.

---

## 5. Жизненный цикл identity snapshot

### 5.1 Когда создаются

1. **На каждый старт сессии.** `SessionManager.start_session` строки 596–603 — снапшот создаётся даже если identity не менялся; это «session lifecycle marker».
2. **На каждый Daily/Deep run.** `_reflection_identity_anchor_snapshot_id` ([reflection_service.py:104–120](src/atman/core/services/reflection_service.py)) — детерминированный UUID из `run_key` гарантирует ровно один anchor per run.
3. **На каждое изменение identity.** `IdentityService` использует приватный helper `_save_with_snapshot` (см. методы `add_core_value`, `update_self_description`, `apply_self_change` в [identity_service.py](src/atman/core/services/identity_service.py)) — каждое сохранение записывает свежий `IdentitySnapshot` через `state_store.create_identity_snapshot`.

### 5.2 Иммутабельность

- **SQL уровень:** триггер `identity_snapshots_immutable BEFORE UPDATE` → `public.prevent_snapshot_modification()` ([0004](migrations/versions/0004_agent_schema.sql):20–26). После 0008/0015 триггер пересоздаётся вместе с таблицей в `agent_{N}` ([0008](migrations/versions/0008_restructure_key_moments.sql):278–281; [0015](migrations/versions/0015_move_subjective_tables.sql):340–345). Триггер выбрасывает `RAISE EXCEPTION 'identity_snapshots are immutable'`.
- **App-уровень:** Pydantic-модель `IdentitySnapshot` ([src/atman/core/models/identity.py](src/atman/core/models/identity.py)) **не** помечена `frozen=True`. То есть из Python снапшот теоретически можно мутировать в памяти — но persistence отбросит UPDATE. Защита по сути одноуровневая (БД).
- **In-memory адаптер.** `InMemoryStateStore` хранит снапшоты в dict, не имея явной защиты от перезаписи; на проде это никогда не используется (адаптеры pg/file — да).

### 5.3 Кто читает

- `SessionManager.start_session` (запись `session.identity_snapshot_id` в `agent_{N}.sessions` строка 630, и в `SessionResult.identity_snapshot_id`).
- `DailyReflectionService` / `DeepReflectionService` через `identity_repo.get_snapshot(sid)` ([reflection_service.py:111](src/atman/core/services/reflection_service.py)).
- Тесты сериализации (`tests/test_serialization_roundtrip.py`).

### 5.4 Связи

- `sessions.identity_snapshot_id` — UUID без FK.
- `key_moments.identity_snapshot_id` — UUID без FK ([0008](migrations/versions/0008_restructure_key_moments.sql):320).
- `ReflectionEvent.identity_snapshot_id` — UUID-поле модели; на уровне БД сейчас рефлексия не пишется, поэтому FK-связи нет, но семантически snapshot живёт долго (триггер запрещает удаление через UPDATE; миграция включает CASCADE только от `public.agents.id`).

---

## 6. Гэпы между спекой и реализацией

> **Серьёзность:** 🔴 critical — нарушает заявленный инвариант; 🟠 major — функционал отсутствует, но не противоречит данным; 🟡 minor — UX/cosmetic / future-work.

### GAP-1 🔴 — Рефлексия не персистится в БД-таблицу `reflections`

- **Спека:** [docs/architecture/REFLECTIONS.md](docs/architecture/REFLECTIONS.md) и миграция [0001](migrations/versions/0001_create_reflections_table.sql)/[0015](migrations/versions/0015_move_subjective_tables.sql) явно объявляют, что micro/daily/deep reflection events хранятся в `agent_{N}.reflections`.
- **Код:** `Micro/Daily/DeepReflectionService` принимает `event_store: ReflectionEventStore`; единственная заводимая реализация — `InMemoryReflectionEventStore` ([in_memory_reflection_store.py](src/atman/adapters/storage/in_memory_reflection_store.py)). Postgres-адаптер не подключён нигде в проводке.
- **Свидетельство:** [reflection_service.py:140, 261, 506](src/atman/core/services/reflection_service.py) — конструкторы; CLI ([cli_reflection.py:303, 345, 391](src/atman/cli_reflection.py)) и `factory.py` инстанцируют только in-memory.
- **Последствие:** рефлексионные события не доживают до bootstrap'а следующей сессии, поэтому `recent_reflections_summary` остаётся пустым ([session_manager.py:584](src/atman/core/services/session_manager.py)).

### GAP-2 🔴 — Reflection никогда не пишет в `pending_human_review`

- **Спека:** [docs/development/work-packages/04-reflection-engine.md](docs/development/work-packages/04-reflection-engine.md) и модель [`PendingReviewDraft`](src/atman/core/models/pending_human_review.py:48) описывают, что Daily/Deep при низкой уверенности **эскалируют** изменения в очередь human review.
- **Код:** ни `DailyReflectionService`, ни `DeepReflectionService` не получают `PendingHumanReviewInbox` через DI; в репо `enqueue(...)` вызывается только тестами (`tests/test_pending_human_review.py`, `tests/test_postgres_subjective_adapters.py`).
- **Свидетельство:** грэпом `PendingReviewDraft` в `src/` — нет ни одного вхождения в core/services. Конструкторы Daily/Deep ([reflection_service.py:259–279, 500–524](src/atman/core/services/reflection_service.py)) не принимают inbox.
- **Последствие:** «# Перед тем как продолжить»-блок ([pending_reviews_context.py](src/atman/adapters/agent/pending_reviews_context.py)) на проде всегда пустой; путь «reflection делится сомнением → bootstrap показывает его агенту в начале сессии» не замкнут.

### GAP-3 🟠 — `SessionManager.finish_session` не запускает micro-reflection автоматически

- **Спека:** [docs/development/work-packages/05-session-manager.md](docs/development/work-packages/05-session-manager.md) и SYSTEM.md описывают micro-reflection как «после-сессионную точку», вызываемую самим менеджером.
- **Код:** в `session_manager.py` `finish_session` пишет `Eigenstate`, обновляет narrative и `SessionResult`, но **не дергает** `MicroReflectionService.reflect`. Грэп `MicroReflectionService` в `session_manager.py` — нет.
- **Последствие:** micro-рефлексия запускается только из CLI/демо/тестов; на проде recent-layer обновляется лишь через `NarrativeService.update_from_identity_and_eigenstate`.

### GAP-4 🟠 — Daily/Deep не вызывают `apply_self_change` / `apply_self_layer_update`

- **Спека:** [`docs/development/work-packages/04-reflection-engine.md`] и комментарии в [`self_applied_change.py`](src/atman/core/models/self_applied_change.py:1) предусматривают «reflection's prerogative — apply with audit».
- **Код:** `apply_self_change` есть в `IdentityService` ([identity_service.py:411](src/atman/core/services/identity_service.py)), `apply_self_layer_update` — в `NarrativeRevisionService` ([narrative_revision.py:321](src/atman/core/services/narrative_revision.py)). Reflection-сервисы пользуются только `narrative_repo.update(...)` (через `_commit_narrative`) и `_propose_*_revision` (которые возвращают строку), но `apply_self_*` не вызывают.
- **Свидетельство:** грэп — единственные внешние вызовы `apply_self_change`/`apply_self_layer_update` сидят в `tests/test_self_applied_changes.py`.
- **Последствие:** аудит-таблица `self_applied_changes` фактически не наполняется в проде; идентичность меняется только через ручные `IdentityService.add_*`/`update_*` методы.

### GAP-5 🟠 — Bootstrap не показывает агенту его собственную «анатомию»

- См. §3.4 выше. **`build_memory_context`** не упоминает уровни рефлексии, доступные tools, существующие памяти/слои. Это критично для запроса (см. §7.2).

### GAP-6 🟠 — Bootstrap не передаёт `habits`, `open_questions`, `emotional_baseline`, `last_eigenstate`, `recent_reflections_summary`

- См. §3.3. Поля есть в моделях и грузятся в `SessionContext` ([session_manager.py:578–585](src/atman/core/services/session_manager.py)), но в `build_memory_context` не попадают.

### GAP-7 🟡 — `cli_reflection.py` обещает non-fixtures режим, который не реализован

- Файл-docstring [cli_reflection.py:1–11](src/atman/cli_reflection.py): «Non-fixtures modes require integration with FileStateStore, which is not yet implemented.»
- Команды `cmd_reflect_*` явно требуют `--fixtures` ([cli_reflection.py:282–285, 329–332, 372–375](src/atman/cli_reflection.py)).

### GAP-8 🟡 — `Identity` модель имеет поля, которых нет в DDL

- В Pydantic-модели [`Identity`](src/atman/core/models/identity.py) поддерживаются `priorities`, `current_focus`, `last_significant_change`, `version`. В DDL `agent_{N}.identity` ([0008](migrations/versions/0008_restructure_key_moments.sql):252–265) этих колонок нет. Адаптеры (`postgres_state_store.py` и т.д. — см. план; в репо `postgres_*` адаптера identity не нашёл) обязаны их класть в JSONB поля или игнорировать. Это потенциальный «тихий drop» при сохранении в Postgres.

### GAP-9 🟡 — `ExperienceRepository` / `SessionRepository` сосуществуют

- `DeepReflectionService` всё ещё принимает `ExperienceRepository` ([reflection_service.py:502](src/atman/core/services/reflection_service.py)), тогда как `DailyReflectionService` — `SessionRepository` ([reflection_service.py:261](src/atman/core/services/reflection_service.py)). Спека [docs/architecture/REFLECTION_FUTURE.md](docs/architecture/REFLECTION_FUTURE.md) описывает миграцию на `SessionRepository` как будущую работу. Это согласовано со спекой как «in-flight», но в коде остаются параллельные пути (CLI имитирует оба контракта через `MockExperienceRepo` ([cli_reflection.py:104–164](src/atman/cli_reflection.py))).

### GAP-10 🟡 — `request_reflection`-tool пишет в `ReflectionRequestQueue` без consumer'а

- Очередь принимает `ReflectionRequest` ([tools.py:355](src/atman/adapters/agent/tools.py)), но в репозитории нет worker'а, который её исполнял бы. `MaintenanceQueue` ([core/ports/maintenance_queue.py](src/atman/core/ports/maintenance_queue.py)) рассчитан на `JobName.*` enrichment-задачи, не на reflection.

### GAP-11 🟡 — Иммутабельность снапшота на app-уровне отсутствует

- `IdentitySnapshot` Pydantic-модель **не** `frozen=True` (см. [src/atman/core/models/identity.py](src/atman/core/models/identity.py)). Защита держится только SQL-триггером. В тестах и in-memory сторадже мутация возможна. См. §5.2.

---

## 7. Точки интеграции для будущих модулей

### 7.1 Skill Manager (см. [docs/development/work-packages/08-skill-manager.md](docs/development/work-packages/08-skill-manager.md))

Спека описывает skill manager как реестр навыков с состояниями (`learning`, `practicing`, `mastered`, `rusty`, …) и operations: discovery, recording, evaluation, recommendation.

Чистые точки расширения:

1. **DI factory** — добавить `skill_store` и `skill_service` в `build_deps` ([factory.py](src/atman/adapters/agent/factory.py)) рядом с `pending_review_inbox`/`reflection_request_queue`. Поле в `AtmanDeps` ([deps.py](src/atman/adapters/agent/deps.py)).
2. **Bootstrap memory** — расширить `build_memory_context` ([instructions.py:100–171](src/atman/adapters/agent/instructions.py)) новым блоком «## Что я умею» / «## Что осваиваю»; получать из `skill_store.list_active_skills(identity_id)`.
3. **Self-awareness блок** (см. §7.3) — там же перечислять навыки как часть собственной «анатомии».
4. **Daily/Deep reflection** — `DailyReflectionService._add_reframing_notes` и `DeepReflectionService._detect_deep_patterns` — добавить шаг «детекция навыка из `key_moments.values_touched`/`structured_markers`», возможно через новый порт `SkillCandidateDetector`. Альтернатива: новый сервис, который слушает `ReflectionEvent` и кладёт `SkillCandidate`-записи (паттерн PLAYBOOK `idempotent-long-running-operations` уже есть).
5. **Session Manager** — `record_event` / `append_key_moment_input` — обогащать `key_moment` ссылками на `skill_id` (новое поле модели; пока нет; БД-таблица `key_moments` уже имеет `structured_markers JSONB`, куда можно складывать без миграции).
6. **Agent tools** — добавить инструмент `record_skill_use(ctx, skill_id, outcome, …)` рядом с `record_key_moment` ([tools.py](src/atman/adapters/agent/tools.py)); зарегистрировать его в `chat()` тем же опциональным сцеплением (`if deps.skill_service is not None: tool_funcs += …`).
7. **Pending human review** — для skill-state transitions, требующих подтверждения, добавить `PendingReviewKind.SKILL_TRANSITION_DOUBT`. Расширить enum в [core/models/pending_human_review.py:24](src/atman/core/models/pending_human_review.py) и SQL CHECK ([0015](migrations/versions/0015_move_subjective_tables.sql):106–111).
8. **БД-схема** — расширить `public.create_agent_schema` (или сделать `extend_agent_schema_0017`-функцию по образцу [0015](migrations/versions/0015_move_subjective_tables.sql)) с таблицей `agent_{N}.skills` и доп. FK в `key_moments.structured_markers` (через UUID-ссылку, без жёсткого FK — паттерн «soft reference» уже используется для `reframing_notes.experience_id`).

### 7.2 Bootstrap self-awareness блок

«Самое чистое» место добавления — расширение [`build_memory_context`](src/atman/adapters/agent/instructions.py:100), сразу **после** identity-блоков и **до** narrative-блоков. Аргументация:

- Не трогаются behavioral instructions (структурные обязательства про честность).
- Доставляется тем же `inject_memory(...)` mode, что и остальная память; работает во всех трёх режимах (`system_prompt`/`assistant_message`/`user_message`).
- Не требует новых полей в `Identity`: содержимое self-awareness блока вычисляется из *рантайма* (какие сервисы/tools у `AtmanDeps` сейчас выставлены), а не из state.

Конкретно:

1. Принять `deps: AtmanDeps` в `build_memory_context`, читать `deps.pending_review_inbox`, `deps.reflection_request_queue`, `deps.affect_detector`, и в фабрике добавить `skill_service` (когда появится).
2. Сразу после блока «Цели» / перед «Нарратив (основа)» добавить новую секцию «## Как я устроена», описывающую (без вранья — только то, что реально подключено):
   - какие виды памяти у меня сейчас есть (fact memory, key moments, narrative core/recent, eigenstate);
   - какие уровни рефлексии существуют и какой я могу запросить через `request_reflection`;
   - какие открытые вопросы рефлексии меня сейчас ждут (если `pending_review_inbox` непустой — link на §6 GAP-2);
   - какие tools у меня под рукой.
3. Для каждого пункта — короткое инвариантное утверждение (1–2 строки), без markdown-перегруза; truncate согласно `deps.truncate_*`.

Альтернативная (более «приватная») точка — `build_instructions` ([instructions.py:62–97](src/atman/adapters/agent/instructions.py)): добавить self-awareness прямо туда. Аргумент против: эти инструкции мыслятся как «структурные правила» и в режиме `assistant_message` не дублируются — а self-awareness важно держать в той же памяти-доставке, которую агент видит как «своё».

### 7.3 Зацепки уже существующие

- `AtmanDeps` уже несёт большинство нужных ссылок (`state_store`, `pending_review_inbox`, `reflection_request_queue`, `affect_detector`-через session_manager).
- `inject_memory` ([memory_injection.py](src/atman/adapters/agent/memory_injection.py)) — единый шлюз доставки, поэтому новый блок будет вести себя одинаково во всех режимах.
- Truncation helper `_truncate_text` ([instructions.py:194–199](src/atman/adapters/agent/instructions.py)) можно переиспользовать.

---

## 8. Открытые вопросы и сомнения

> Решений тут нет — это список того, что осталось неясным/противоречивым и должно быть осознанно решено в плане.

1. **Кто и когда вызывает Daily/Deep reflection в проде?** В коде нет планировщика, который бы дергал `DailyReflectionService.reflect`. Должен ли это делать APScheduler (упомянут в `pyproject.toml`/AGENTS.md как «планируемая зависимость»), или event-driven из `finish_session`, или внешний worker через `maintenance_jobs`? Связано с GAP-1/GAP-2/GAP-3.

2. **`reflections` — таблица per-agent, но `experience_refs UUID[]` без FK.** Намеренная свобода (soft reference) или потенциальный gap data integrity? То же касается `reframing_notes.experience_id` (хотя оно после 0014 уже nullable и пути писать его не остались).

3. **Eigenstate live inside `narrative.eigenstate JSONB`** ([0008](migrations/versions/0008_restructure_key_moments.sql):292). При этом модель `Eigenstate` — отдельная сущность с `id`. Где хранится `id`? Сериализован ли он внутри JSONB? Если да — что значит `state_store.save_eigenstate` API ([state_store.py:349](src/atman/core/ports/state_store.py))? Возможно, реальный adapter пишет в столбец, теряя UUID — стоит проверить, но это уже выходит за read-only периметр.

4. **`identity_snapshots.state JSONB`** хранит сериализованную `Identity` целиком (включая поля, которых нет в `identity`-таблице). Это значит, что snapshot — единственный источник правды о «полной» истории; restore идёт из JSONB. Должны ли мы это считать инвариантом и тестить отдельно?

5. **Конфликт `ExperienceRepository` ↔ `SessionRepository`.** Спека REFLECTION_FUTURE декларирует переход; сегодня Deep ещё на `ExperienceRepository`, Daily — на `SessionRepository`, CLI имитирует оба контракта в одном Mock-классе ([cli_reflection.py:58–164](src/atman/cli_reflection.py)). Когда заявляется DoD «Deep тоже на `SessionRepository`»?

6. **`micro_reflection` без `reflection_run_key`.** `MicroReflectionService` не присваивает `reflection_run_key` ([reflection_service.py:198–204](src/atman/core/services/reflection_service.py)), хотя у Daily/Deep это базовый инвариант идемпотентности. Заявлено ли это сознательно («micro идёт по session_id, идемпотентность через `event_store.save` дубликат-проверку»)?

7. **`PendingReview.created_by`** — строка вида `'reflection_daily'`. Не та же ли это семантика, что и `SelfChangeActor`? Если да, почему два разных типа? Если нет — где документировано различие?

8. **`pending_review_inbox` в bootstrap-блоке появляется до `# Кто я`** ([runner.py:761–765](src/atman/adapters/agent/runner.py)), то есть «вопросы рефлексии» агент видит **раньше**, чем «кто я». Не противоречит ли это спеке Session Manager («личность подгружается первой»)?

9. **Bootstrap бесшумно бутстрапит identity, если её нет** ([factory.py](src/atman/adapters/agent/factory.py) → `IdentityService.bootstrap_identity`). Никаких journal-записей, никакого `PendingReview('first_bootstrap')` — то есть человек не узнает о факте «у этого agent_id создалась новая жизнь». Соответствует ли это намерению MANIFEST'a?

10. **`narrative.eigenstate JSONB` mutates без оптимистики.** `NarrativeService.update_from_identity_and_eigenstate` обновляет тот же документ, что и `NarrativeRevisionService.update_recent_layer`. Если micro-reflection (recent layer) и session finish (eigenstate) бегут параллельно — обе используют `expected_updated_at`, но один пишет eigenstate, другой — recent_layer. Гонка возможна; разрешена ли она?

11. **`record_key_moment` — единственный tool, упомянутый в `build_instructions`.** Между тем агент по факту имеет несколько других (`log_experience`, `restart_session`, …). Должна ли self-awareness часть инструкций перечислять весь набор, или только «эмоционально-связанные»?

12. **`mock_reflection_model` в проде.** Если LLM-endpoint падает, `OpenAIReflectionModel._call_with_retry` после `max_retries` бросает `OllamaReflectionError`. Какая политика fallback'а у Reflection Engine — fail loudly, или подменять на mock? Пока — fail loudly (см. [openai_reflection_model.py:109](src/atman/adapters/reflection/openai_reflection_model.py)), но в проводке это не зафиксировано документом.

---

_Конец отчёта._
