# Стандарт разработки Atman

_Статус: рабочий контракт для людей и агентов._

Этот документ нужен не для красоты архитектуры, а для координации параллельной
разработки. Если несколько агентов реализуют разные части Atman, они должны
использовать одинаковые слова, одинаковые границы ответственности и одинаковые
контракты. Иначе система быстро превратится в набор несовместимых локальных
решений.

## 1. Главный принцип разработки

Atman может быть сложным внутри, но должен оставаться простым снаружи.

Для пользователя или интегратора Atman должен выглядеть как один понятный
runtime:

```text
agent session -> Atman context -> agent work -> Atman update
```

Внутренние компоненты не должны становиться отдельными продуктами, сервисами или
деплойными требованиями без явного архитектурного решения.

## 2. Что считаем ядром, а что адаптерами

### Core

Core - это доменная логика Atman, которая не должна зависеть напрямую от mem0,
OpenClaw, конкретной LLM, конкретной файловой структуры или конкретного
scheduler.

В Core входят:

- модели фактов, опыта, идентичности, нарратива, неопределенности, навыков;
- правила переходов между состояниями;
- сборка `PersonalitySnapshot`;
- session lifecycle;
- reflection lifecycle;
- governance, audit, snapshots, migrations.

### Adapter

Adapter - это перевод между Atman Core и внешней системой.

Примеры:

- `Mem0MemoryBackend` - адаптер к mem0;
- `OpenClawWorkspaceAdapter` - адаптер к workspace-файлам OpenClaw;
- `CursorProjectAdapter` - будущий адаптер к Cursor-окружению;
- `DockerRuntimeAdapter` - упаковка запуска;
- `HttpAgentAdapter` - внешний API для агентов;
- `LLMProvider` - адаптер к OpenAI/Anthropic/local model.

Запрещено: писать доменную логику Atman так, чтобы она напрямую знала детали
OpenClaw или mem0 SDK.

### Domain Subsystems (co-located adapters with their own port)

Большие подсистемы со своей внутренней архитектурой (детектор + baseline +
метрики + лексиконы; skill-loop + store + retriever; и т.д.) допускается
держать в отдельном пакете на уровне `src/atman/<subsystem>/` вместо того,
чтобы распылять их по `core/` и `adapters/`. Это «co-located adapter»: пакет
сам по себе ведёт себя как adapter (содержит конкретные реализации,
зависит от внешних библиотек), но имеет собственный порт для интеграции с
Core.

Контракт для такого пакета:

1. **Порт живёт в `core/ports/<subsystem>.py`.** Core-сервисы зависят
   только от порта, никогда от конкретных классов подсистемы.
2. **Пакет может импортировать `core/models/*` и `core/ports/*`,** но **не**
   `core/services/*` и **не** другие doman subsystems.
3. **Core не импортирует подсистему статически.** Когда default-инстанс
   нужен в Core-сервисе, его собирает composition root (`adapters/agent/factory.py`,
   CLI, или тест) и инжектит через порт.
4. **Internal layering внутри пакета** свободно: подсистема может иметь
   собственные models / detector / store без подражания структуре `core/adapters/`.

Текущие domain subsystems:

| Пакет | Порт | Owner |
| --- | --- | --- |
| `atman.affect` | `core/ports/affect.py` (`AffectPort`) | детектор аффекта, baseline, NRC emolex, refusal-детектор |
| `atman.skills` | `atman.skills.port` (TODO: переезд в `core/ports/skill_manager.py`) | skill-loop, SkillManagerPort, store, retriever |

Если подсистема выросла из тривиального adapter'а и требует собственной
under-the-hood-архитектуры (несколько файлов, отдельные unit-тесты,
собственные модели) — добавляйте новую строку в таблицу выше и заводите
порт в `core/ports/` тем же коммитом.

## 3. Минимальный runtime path

Перед deep reflection, proactive engine, skill marketplace и сложной affective
regulation должен стабильно работать минимальный путь:

```text
1. start_session
2. build_personality_snapshot
3. deliver_snapshot_to_agent
4. capture_session_events
5. end_session
6. write_eigenstate
7. update_recent_narrative
8. next start_session uses updated narrative first
```

Этот путь является главным критерием MVP. Все остальные компоненты должны
улучшать его, а не заменять.

## 4. Общий словарь

### Atman

Психологический runtime агента. Не нижний исполнитель задач, а слой
непрерывности, памяти опыта, самоописания и рефлексии.

### Lower Agent / Рабочий агент

Агент, который выполняет пользовательскую задачу: пишет код, отвечает,
планирует, вызывает инструменты. Atman не равен рабочему агенту, но может
формировать для него контекст и принимать от него следы опыта.

### Session

Ограниченный эпизод взаимодействия рабочего агента с пользователем или задачей.
Сессия имеет начало, активную фазу и завершение. Не путать с процессом ОС или
LLM-call.

### Session Event

Структурированное событие внутри сессии: сообщение, решение, конфликт, обещание,
ошибка, изменение тона, значимый момент.

### Key Moment

Событие сессии, которое важно для опыта или идентичности. Не каждый log line -
key moment.

### Fact

Проверяемое утверждение о том, что было, кто участвовал, что решено, где
источник и насколько запись актуальна. Fact не содержит психологического вывода.

Правильно:

```text
Пользователь попросил подготовить стандарт разработки Atman.
```

Неправильно:

```text
Пользователь боится техдолга, потому что не доверяет системе.
```

Вторая фраза может быть гипотезой или reflection, но не fact.

### Experience

Пережитый агентом эпизод от первого лица: что произошло, как это было окрашено,
почему было значимо, какие ценности/принципы задело, что изменилось.

Experience нельзя ретроспективно "дорисовывать" как будто агент чувствовал это
в моменте. Если окраска неполная, используется `incomplete_coloring`.

### Reflection

Осмысление уже записанного опыта. Reflection может добавлять новый взгляд, но не
переписывает оригинальный experience.

### Identity

Структурированное самоописание Atman: ценности, принципы, привычки, цели,
открытые вопросы, ограничения, история изменений.

### Self-Narrative / Narrative

Письмо Atman самому себе в первое лицо, которое читается в начале следующей
сессии первым. Это не summary и не identity dump. Это точка самоузнавания.

### Eigenstate

Снимок эмоционально-когнитивного состояния на завершении сессии: где Atman
остановился, что осталось открытым, какой тон и нагрузка.

### Uncertainty

Открытый вопрос, гипотеза или противоречие, которое не закрыто опытом. Не
маскировать uncertainty под факт.

### PersonalitySnapshot

Универсальный объект, который Core собирает для старта сессии. Snapshot затем
может быть превращен адаптером в файлы, prompt, API payload или MCP resource.

### IntegrationAdapter

Компонент, который доставляет `PersonalitySnapshot` конкретной агентской среде и
принимает от нее session output.

### MemoryBackend

Порт Core для записи и поиска памяти. mem0, file storage, in-memory storage или
другая БД - реализации этого порта.

### StateStore

Порт для структурированного состояния Atman: identity, narrative, snapshots,
jobs, migrations, audit. Не сводить весь `StateStore` к mem0.

### Governance

Правила того, какие изменения можно применять автоматически, какие требуют
review, а какие запрещены.

### Audit Trail

Неизменяемый журнал значимых изменений: кто/что/когда/почему изменил память,
нарратив, identity, skills, relationships или конфигурацию.

## 5. Запрещенные смешения

### Fact != Experience

Fact отвечает "что известно". Experience отвечает "как это было прожито".

### Experience != Reflection

Experience записывает первичный слой. Reflection добавляет новый взгляд позже.

### Habit != Principle

Habit описывает повторяемое поведение. Principle описывает выбранную норму.
Повторяемое поведение не становится принципом автоматически.

### Skill != Memory

Skill - переносимый способ действия. Memory - запись о факте/опыте/рефлексии.
У навыка может быть история применения, но он не равен этой истории.

### Narrative != Summary

Summary пересказывает. Narrative восстанавливает "я сейчас".

### Adapter != Core

Если модуль содержит слова `OpenClaw`, `Cursor`, `mem0`, `Anthropic`, `Docker`,
он почти наверняка adapter или infrastructure, а не Core.

## 6. Канонические имена модулей

Когда начнется код, использовать такие имена пакетов/директорий как стартовую
точку. Если язык или framework требует другой стиль, сохранить смысл.

```text
atman/
  core/
    models/
      fact.py
      experience.py
      identity.py
      narrative.py
      eigenstate.py
      uncertainty.py
      skill.py
      relationship.py
      snapshot.py
    ports/
      memory_backend.py
      state_store.py
      llm_provider.py
      clock.py
      event_bus.py
      integration_adapter.py
    services/
      session_lifecycle.py
      snapshot_builder.py
      reflection_runner.py
      narrative_writer.py
      governance.py
      audit.py
      migration_runner.py
  adapters/
    memory/
      mem0_backend.py
      in_memory_backend.py
      file_backend.py
    workspace/
      openclaw_adapter.py
      file_workspace.py
    llm/
      openai_provider.py
      anthropic_provider.py
      fake_provider.py
    runtime/
      cli.py
      http_api.py
      scheduler.py
  infra/
    config.py
    logging.py
    health.py
    export_import.py
```

Не обязательно создать все сразу. Но если компонент появляется, он должен лечь в
соответствующую область.

## 7. Канонические имена доменных объектов

Использовать эти названия в коде, документах, тестах и issue.

```text
FactRecord
ExperienceRecord
SessionExperience
KeyMoment
FeltSense
ContextHalo
ReflectionEvent
IdentityState
IdentitySnapshot
SelfNarrative
NarrativeThread
Eigenstate
UncertaintyItem
SkillManifest
SkillUsage
RelationshipState
PersonalitySnapshot
SessionContext
SessionResult
SessionEvent
MemoryQuery
MemorySearchResult
AuditEvent
GovernanceDecision
MigrationRecord
HealthReport
```

Если нужен другой термин, сначала добавить его в этот словарь или в отдельный
ADR. Не вводить синонимы вроде `memory_item`, `note`, `profile`, `persona`,
`soul_state`, если уже есть канонический термин.

## 8. Имена переменных

Предпочитаемые имена:

```text
agent_id
user_id
session_id
run_id
tenant_id
experience_id
fact_id
identity_snapshot_id
narrative_id
thread_id
skill_name
skill_version
relationship_id
source_ref
created_at
updated_at
recorded_at
loaded_at
last_accessed_at
access_count
confidence
importance
salience
emotional_valence
emotional_intensity
depth
incomplete_coloring
evidence_refs
schema_version
```

Не использовать:

```text
uid        # непонятно чей id
data       # слишком общее
memory     # слишком общее без типа
profile    # смешивает identity/user/persona
state      # слишком общее без контекста
soul       # допустимо как external file name, не как core model
```

## 9. Идентификаторы и область видимости

Минимальная область изоляции:

```text
tenant_id -> agent_id -> user_id -> session_id
```

Для локального прототипа `tenant_id` может быть фиксированным, но модель данных
должна оставлять место под него. Иначе managed/self-host multi-agent режим будет
сложно добавить позже.

Правила:

- `agent_id` идентифицирует Atman/личность агента.
- `user_id` идентифицирует человека или внешнего субъекта отношений.
- `session_id` идентифицирует эпизод взаимодействия.
- `run_id` идентифицирует технический запуск job/worker/agent process.
- Не использовать `user_id` mem0 как единственный идентификатор Atman. Для mem0
  можно маппить `agent_id`/`user_id`, но это деталь адаптера.

## 10. Версионирование схем

Любая persistable структура должна иметь версию:

```text
schema_version
```

Минимально версионируемые сущности:

- `FactRecord`;
- `ExperienceRecord`;
- `IdentityState`;
- `SelfNarrative`;
- `Eigenstate`;
- `UncertaintyItem`;
- `SkillManifest`;
- `RelationshipState`;
- `PersonalitySnapshot`.

Если структура меняется несовместимо, добавить migration. Не полагаться на
"пока данных мало".

## 11. Storage boundaries

### Factual Memory

Хранит проверяемые факты и связи. Может быть реализована через mem0, но Core
видит только `MemoryBackend`.

### Experience Store

Хранит пережитый опыт. Оригинальный опыт immutable. Разрешены только добавочные
слои: `reframing_notes`, access metadata, derived indexes.

### Identity Store

Хранит текущее самоописание и историю снапшотов. Не должен быть просто markdown
файлом. Markdown может быть presentation/export.

### Narrative Store

Хранит текущий narrative и архив прошлых narrative. Текущий `NARRATIVE.md` в
OpenClaw - adapter output, не единственный источник правды.

### Job Store

Хранит runs micro/daily/deep, статусы, ошибки, retry, idempotency keys.

### Audit Store

Хранит неизменяемый журнал значимых изменений.

## 12. Ports: минимальные контракты

### MemoryBackend

```text
add_fact(record: FactRecord) -> FactRecord
get_fact(fact_id) -> FactRecord | None
search_facts(query: MemoryQuery) -> list[MemorySearchResult]
list_recent_facts(agent_id, limit) -> list[FactRecord]
```

Нельзя заставлять Core передавать параметры конкретного mem0 SDK.

### StateStore

```text
load_identity(agent_id) -> IdentityState
save_identity(identity, expected_version=None) -> IdentityState
load_narrative(agent_id) -> SelfNarrative
save_narrative(narrative, expected_version=None) -> SelfNarrative
append_experience(experience) -> ExperienceRecord
append_audit_event(event) -> AuditEvent
```

`expected_version` нужен для защиты от потерянных обновлений.

### IntegrationAdapter

```text
deliver_snapshot(snapshot: PersonalitySnapshot, target) -> DeliveryResult
collect_session_result(source) -> SessionResult
```

OpenClaw adapter может писать `NARRATIVE.md`, `SOUL.md`, `AGENTS.md`, `USER.md`,
но Core должен работать и без этих файлов.

### LLMProvider

```text
complete(request) -> LLMResponse
```

В тестах всегда должен быть `FakeLLMProvider`.

### Clock

```text
now() -> datetime
```

Не использовать прямой `datetime.now()` в доменной логике. Это ломает тесты
decay, scheduler и timeline.

## 13. Session lifecycle

Канонический lifecycle:

```text
start_session
  -> load current identity/narrative/eigenstate/recent memory
  -> build PersonalitySnapshot
  -> deliver snapshot via IntegrationAdapter

during_session
  -> collect SessionEvent
  -> identify KeyMoment
  -> optionally mark incomplete_coloring

end_session
  -> produce SessionResult
  -> write Eigenstate
  -> append SessionExperience
  -> update Recent Layer
  -> enqueue micro reflection if needed
```

Любой компонент, который участвует в сессии, должен явно указать, на каком шаге
он работает.

## 14. Reflection lifecycle

Три уровня:

### Micro

Цель: бесшовность следующей сессии.

Разрешено:

- обновить recent layer narrative;
- записать checkpoint;
- отметить незавершенную thread.

Запрещено:

- менять core identity;
- менять принципы;
- делать глубокие выводы из одного слабого сигнала.

### Daily

Цель: собрать день, обновить рабочий контекст, не ломая core.

Разрешено:

- обновить user/relationship context;
- добавить daily experience;
- предложить изменения identity как draft/review.

### Deep

Цель: паттерны, пересмотр, narrative revision, identity snapshots.

Разрешено:

- менять identity при наличии evidence;
- закрывать/открывать uncertainty;
- создавать snapshot;
- инициировать governance review.

## 15. Governance modes

Каждое изменение persistent state должно попадать в один из режимов:

```text
auto          # безопасное автоматическое изменение
review        # требует подтверждения или отдельного review flow
locked        # запрещено менять обычными процессами
experimental  # гипотеза с ограниченным сроком жизни
```

Примеры:

- salience/access_count: `auto`;
- recent narrative: `auto`;
- новый principle: `review`;
- изменение core boundary: `locked` или `review` с ручным подтверждением;
- гипотеза о паттерне поведения: `experimental`.

## 16. Audit rules

AuditEvent обязателен для:

- изменения IdentityState;
- изменения Core Layer narrative;
- закрытия/удаления NarrativeThread;
- изменения principle;
- установки/удаления skill;
- удаления, скрытия или исправления memory;
- import/export;
- migration;
- изменения governance status;
- запуска deep reflection.

AuditEvent должен отвечать:

```text
what changed?
who/what changed it?
when?
why?
based on what evidence?
can it be rolled back?
```

## 17. Deployment guardrails

Каждый новый work package должен явно указать:

- как он запускается локально без внешних сервисов;
- какие env vars нужны для production-like режима;
- какие persistent данные он создает;
- есть ли migration;
- есть ли healthcheck;
- как сделать export/import;
- как он деградирует без LLM/mem0/vector store;
- какой adapter boundary защищает Core.

Целевой self-host MVP:

```text
atman service/worker
state backend: Postgres + pgvector или другой один backend
LLM/embedding provider через env
docker compose для запуска
```

Не добавлять новый обязательный сервис в runtime без отдельного ADR.

## 18. Конфигурация

Все настройки делятся на:

### Runtime config

Меняет запуск, но не личность:

```text
ATMAN_ENV
ATMAN_LOG_LEVEL
ATMAN_STATE_URL
ATMAN_MEMORY_BACKEND
ATMAN_LLM_PROVIDER
ATMAN_EMBEDDING_PROVIDER
```

### Agent config

Относится к конкретному Atman:

```text
agent_id
default_language
integration_adapter
reflection_policy
governance_policy
```

### Personality state

Не хранить в `.env`. Это доменное состояние:

- identity;
- narrative;
- principles;
- relationships;
- uncertainty.

### Локальная разработка: uv

По возможности использовать **[uv](https://github.com/astral-sh/uv)** для окружения и запуска: `uv venv`, `uv pip install -e ".[dev]"`, **`uv run`** для `python`, `pytest`, `ruff`, `pyright` и других dev-команд — так проще воспроизводить шаги и не смешивать глобальный Python. Подробности и примеры — в **`AGENTS.md`** (раздел _uv — рекомендуемый workflow_). `pip` допустим, если `uv` недоступен.

## 19. Ошибки и деградация

Atman должен уметь честно работать в неполном режиме:

- нет mem0 -> использовать file/in-memory backend в dev или вернуть явный degraded status;
- нет LLM -> не выполнять reflection, но сохранить session result;
- не удалось доставить snapshot -> не начинать session silently;
- не удалось обновить narrative -> сохранить ошибку в job/audit и не терять session result;
- конфликт версий state -> retry или manual review, не перезаписывать молча.

Запрещено скрывать деградацию под успешный результат.

## 20. Тестовые соглашения

Каждый модуль должен иметь:

- unit tests для доменных инвариантов;
- tests через fake adapters;
- один smoke/integration path для ручного запуска;
- fixtures с минимальными валидными объектами.

Обязательные fake-компоненты:

```text
InMemoryMemoryBackend
InMemoryStateStore
FakeLLMProvider
FrozenClock
FakeIntegrationAdapter
```

Тесты не должны требовать реальные API keys, mem0 server, OpenClaw workspace или
интернет.

## 21. Definition of Done для любого пакета

Пакет считается готовым только если:

- использует канонические термины из этого документа;
- не смешивает Fact/Experience/Reflection/Identity/Skill;
- имеет явные ports/adapters;
- запускается локально без внешних сервисов;
- имеет тесты для основных инвариантов;
- документирует команды запуска;
- описывает persistent данные и schema_version;
- имеет health/degraded story;
- не добавляет обязательный runtime-сервис без ADR;
- не привязан напрямую к mem0/OpenClaw/конкретной LLM в Core;
- **актуализирует `docs/architecture/SYSTEM_MAP.md` (+ `SYSTEM_MAP-ru.md`)** —
  новые модули/порты/адаптеры/сервисы/точки входа/сценарии/edge-cases/регрессии
  отражены в соответствующих разделах карты (см. §26).

### Definition of Demo (наглядная демонстрация)

Пакет, который **меняет поведение для пользователя или интегратора** (новый work
package, новый CLI, новый публичный API, новый поток данных), считается полностью
готовым для review только если ревьюер может **воспроизвести сценарий без чтения
исходников**.

Минимальный набор артефактов:

1. **Человекочитаемое описание фичи** — что изменилось и какие инварианты
   важны. Размещение: каталог **`docs/features/<slug-фичи>/`** с парой **`README.md`**
   (английский) и **`README-ru.md`** (русский) плюс при необходимости ТЗ в
   `docs/development/work-packages/`. Порядок правок: сначала английская версия,
   затем синхронизация русской (как для корневого README).
2. **Воспроизводимый сценарий** — одна команда или короткая последовательность
   без интерактива, либо сценарий в `Makefile` (например `make demo-<feature>`),
   либо скрипт под `src/demo_*.py`, документированный в `AGENTS.md`. Консольный
   вывод демо и CLI — по **`AGENTS.md`** (_Пользовательский вывод в терминале (Rich)_):
   **Rich**, **`atman.term`**, при необходимости **`demo_pace()`**; для прогона без пауз —
   **`make demo-*-fast`** или `ATMAN_DEMO_PACE=off`.
3. **Фиксированные входы** — минимум одна фикстура или seed-данные в `fixtures/`
   (или эквивалент), на которых строится сценарий.
4. **Контракт в тестах** — инварианты, которые демонстрация иллюстрирует,
   должны быть защищены автотестами (`pytest`).
5. **Реестр фич для TUI и Web Dashboard** — добавить запись `FeatureInfo` в кортеж
   **`FEATURES`** в `src/atman/tui/features_registry.py`: `slug`, `title`, `summary`,
   `doc_dir` (каталог под `docs/features/<slug>/`), `related_paths`, пара демо
   (`DemoCommand` paced/fast с корректным `ATMAN_DEMO_PACE` в `env`), `test_globs`.
   TUI (`features_tab`) и веб-дашборд читают только этот реестр; без записи фича
   не появится в списке демо и не подтянет README во вкладке фич.

Успешный прогон демонстрации: команды из пункта 2 выполняются в чистом окружении
(после `pip install -e ".[dev]"`), **без внешних сервисов и API keys**, завершаются
с ненулевым кодом только при ошибке; вывод позволяет убедиться, что ключевой поток
работает (создание записи, чтение, поиск, деградация и т.д. — по смыслу фичи).

Агент (локальный или облачный) обязан обновить эти артефакты в том же PR, что и
код, либо явно указать N/A с причиной (например «только правка опечатки в
комментарии»).

## 22. ADR: когда нужен архитектурный документ

ADR обязателен, если изменение:

- добавляет новый обязательный сервис;
- меняет формат `PersonalitySnapshot`;
- меняет lifecycle session/reflection;
- меняет storage boundary;
- меняет governance для identity/principles;
- добавляет новый тип памяти;
- делает breaking change в persistent schema;
- меняет целевой deployment path.

ADR должен содержать:

```text
context
decision
alternatives considered
consequences
migration impact
deployment impact
rollback plan
```

## 23. Порядок реализации

Рекомендуемый порядок, чтобы не закопаться:

1. Core models + ports + fake adapters.
2. PersonalitySnapshot builder.
3. Minimal session start/end.
4. Narrative recent layer update.
5. File/local StateStore with schema versions.
6. MemoryBackend adapter boundary, затем mem0 adapter.
7. CLI doctor/health/export/import.
8. OpenClaw IntegrationAdapter.
9. Micro reflection.
10. Audit trail.
11. Identity snapshots.
12. Daily/deep reflection.
13. Reality/Affect.
14. Skill Manager.
15. Ambient/Proactive.
16. Admin/Control Room.

Если агент хочет начать с пункта 12 до пункта 3, он должен явно объяснить, как
его результат будет подключен к минимальному runtime path.

## 24. Структура репозитория

Каждый файл должен лежать в строго определённом месте.
Полная спецификация структуры `docs/` — в `docs/design/DESIGN_docs_structure.md`.
Правило простое: не знаешь куда — смотри таблицу ниже или спроси.

### Корень репозитория `/`

Только то, что GitHub и инструменты ожидают найти в корне:

```text
README.md / README-ru.md   — точка входа для людей
MANIFEST.md / MANIFEST-ru.md
AGENTS.md                  — инструкции для агентов (только EN)
CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / LICENSE
Makefile
pyproject.toml / uv.lock
.gitignore / .gitattributes / .markdownlint.json / .pre-commit-config.yaml
.github/                   — Actions workflows, шаблоны PR/issues
.cursor/                   — правила для Cursor
src/                       — исполняемый код
tests/                     — тесты
e2e/                       — end-to-end сценарии
fixtures/                  — тестовые фикстуры
reports/                   — отчёты о сессиях и реализации
scripts/                   — служебные скрипты (codemap, docs, eval)
```

Запрещено класть в корень: design-документы, отчёты, HTML-файлы сайта,
скрипты-демо, исследования, work packages, README к отдельным модулям.

### `/docs` — вся документация

```text
docs/
  architecture/            — ЧТО такое система (стабильное, прорецензированное)
    SYSTEM.md / -ru.md
    SYSTEM_MAP.md / -ru.md   ← авто-обновляется кодмапом
    ADR/                     ← Architecture Decision Records (ADR-NNN-title.md)
    codemap/                 ← авто-генерируется скриптом, не редактировать руками
      STARTUP_DEPS.md / -ru.md
      TEST_ENV.md / -ru.md
      ENDPOINTS.md / -ru.md
      DELTA_REPORT.md / -ru.md
      UNDOCUMENTED.md / -ru.md

  design/                  — КАК строим конкретные вещи (эволюционирует)
    DESIGN_*.md / -ru.md
    *-design.md / -ru.md

  development/             — процесс и стандарты
    DEVELOPMENT_STANDARD.md (этот файл)
    work-packages/           ← ТЗ на реализацию, NN-name.md

  features/                — пользовательские гайды по фичам
    <slug>/
      README.md / README-ru.md

  ops/                     — как запускать и эксплуатировать Atman
    УСТАНОВКА.md
    ...

  research/                — что изучалось; нет обязательства действовать
  ideas/                   — гипотезы, ещё не в работе
  archive/                 — устаревшее; только git mv, не удалять

  content/                 — копии для GitHub Pages; НЕ редактировать вручную
    README.md / -ru.md
    MANIFEST.md / -ru.md
    SYSTEM.md / -ru.md
    SYSTEM_MAP.md / -ru.md

  (ассеты сайта)
    CNAME / index.html / document.html / demo.html / pic/
```

### Быстрая таблица: куда класть новый документ

| Создаёшь... | Папка |
|-------------|-------|
| Архитектурное решение (принято, стабильно) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Design doc (в процессе, эволюционирует) | `docs/design/DESIGN_*.md` |
| Гайд для пользователя фичи | `docs/features/<slug>/README.md` + `README-ru.md` |
| ТЗ на реализацию (work package) | `docs/development/work-packages/NN-name.md` |
| Операционный runbook (установка, мониторинг) | `docs/ops/` |
| Исследование, сравнение, эксперимент | `docs/research/` |
| Гипотеза, ещё не в работе | `docs/ideas/` |
| Отчёт о реализации / сессии | `reports/` |

### Правила для агентов

- **Создал новый документ** — найди строку в таблице выше; не знаешь — спроси.
- **Не создавай новые папки** в корне и в `docs/` без явного решения в PR.
- **Не редактируй `docs/content/`** — файлы там перезаписываются автоматически.
- **Не кладёт в `docs/archive/`** — туда только переносят через `git mv`.
- **Feature guide** (`docs/features/<slug>/`) — только пара `README.md` + `README-ru.md`.
- **Work package** — только в `docs/development/work-packages/`, имя `NN-name.md`.
- **ADR** — только в `docs/architecture/ADR/`, имя `ADR-NNN-short-title.md`.
- **Design doc** — префикс `DESIGN_` или суффикс `-design.md`.
- **Двуязычность**: `docs/architecture/`, `docs/design/`, `docs/ops/` требуют `-ru.md` пару.
  EN пишется первым, RU — следом. `docs/research/` и `docs/ideas/` — RU опционально.
- **`SYSTEM_MAP.md`**: обновляется кодмапом автоматически (§1 таблицы).
  §2–§5 (сценарии, edge cases, регрессии) — обновлять руками в том же PR, что и код.
- **`README.md` / `MANIFEST.md` / `SYSTEM.md`**: правишь EN → сразу синхронизируй RU →
  запусти `make sync-site-content` (обновит `docs/content/`).
- **Скрипты-демо** (`demo.py`, `full_demo.sh`) — в `src/` или удалить после merge.
- **`uv`**: для установки и запуска предпочитать `uv run`, `uv pip install`.

## 25. Checklist перед началом новой задачи

Перед реализацией агент должен ответить в описании PR или рабочем документе:

- какой доменный объект я меняю?
- это Core или Adapter?
- какие ports я использую?
- какие persistent структуры появляются?
- какая schema_version?
- какие инварианты защищаю тестами?
- как запустить без внешних сервисов?
- что будет в degraded mode?
- нужен ли audit?
- нужен ли governance decision?
- как это влияет на deployment?
- какие разделы `docs/architecture/SYSTEM_MAP.md` (модули / интеграции /
  сценарии / edge cases / регрессии) изменятся, и какие тесты их закрывают?

## 26. Карта системы и тестовое покрытие

`docs/architecture/SYSTEM_MAP.md` (+ парный `SYSTEM_MAP-ru.md`) — структурированный
инвентарь кодовой базы: модули, интеграции, пользовательские сценарии,
нестандартные входы, известные регрессии. Карта используется как **план
покрытия тестами** и как точка навигации для агентов и людей.

### 26.1. Когда обязательно обновлять карту

Карта обновляется в том же PR, что и код, если изменение:

- добавляет, удаляет или переименовывает модуль (файл под `src/atman/`);
- добавляет или меняет публичный класс/функцию модуля;
- добавляет, удаляет или меняет порт (`core/ports/`) или адаптер (`adapters/`);
- меняет проводку сервиса (`core/services/`) — какой порт/адаптер используется;
- добавляет точку входа: CLI-команду, вкладку TUI, страницу веб-дашборда, демо;
- меняет или добавляет e2e-сценарий;
- добавляет валидацию входа, защиту от дублей, обработчик парсинга JSON/JSONL,
  governance-проверку или поведение при конкуренции (закрывает «GAP» из §4 карты);
- чинит регрессию или известный баг (запись в §5 карты + regression-тест в `tests/`).

### 26.2. Привязка тестов к разделам карты

Новые тесты должны быть привязаны к соответствующему разделу карты:

| Раздел карты | Тип тестов | Назначение |
|--------------|------------|------------|
| §1 Модули | unit | нормальный путь, граничные случаи, ошибки для модулей с входом → преобразованием → решением → результатом |
| §2 Интеграции | integration | каждая связка сервис↔порт, CLI↔сервис, demo↔реальные объекты, цепочка рефлексии |
| §3 Сценарии | system / e2e | пользовательские пути A–G; запись→чтение→преобразование→состояние |
| §4 Edge cases | unit / integration | пустой ввод, длинный ввод, дубли, неправильный формат, частичные данные, повторный запуск, неожиданный порядок шагов, отсутствующий файл/запись, сломанный JSON/JSONL |
| §5 Регрессии | regression | по одному тесту на каждый известный баг — гарантирует, что он не вернётся |

### 26.3. Что должно быть в описании PR

В описание PR нужно явно вписать:

- какие пункты карты затронуты (например, «§1.3 — добавлен `SessionManagerService`,
  §2.1 — связка с `SessionStore`, §3 — новый сценарий H»);
- какими тестами эти пункты покрыты (имя файла теста + название теста);
- если затрагивается §4 GAP — какой именно GAP закрыт.

### 26.4. Двуязычная синхронизация

`SYSTEM_MAP.md` — канонический английский. Сначала правится он, затем
синхронизируется `SYSTEM_MAP-ru.md`. То же правило, что и для пар
`README.md`/`README-ru.md`, `MANIFEST.md`/`MANIFEST-ru.md`,
`SYSTEM.md`/`SYSTEM-ru.md`.

`make sync-site-content` карту не копирует — она остаётся в `docs/architecture/`.

### 26.5. Тесты-страховки агентной разработки

Семь файлов в `tests/` — это **жёсткие контракты системы**, которые ловят
тихие поломки при изменении кода агентами. Они обязаны обновляться вместе с
кодом в том же PR. Если агент внёс изменение из левой колонки, но не обновил
файл из правой — PR не готов.

| Файл-страховка | Что фиксирует | Когда расширять |
|----------------|---------------|-----------------|
| `tests/test_state_store_contract.py` | контракт порта `StateStore` (параметризован по реализациям) | новый метод в `core/ports/state_store.py`; новая реализация порта (добавить параметр в `@pytest.fixture(params=[...])`) |
| `tests/test_serialization_roundtrip.py` | round-trip JSON и persistence-after-restart для всех персистируемых сущностей | переименование/удаление поля в `Identity`, `ExperienceRecord`, `NarrativeDocument`, `Eigenstate`; смена сериализации |
| `tests/test_golden_schema.py` | inline-эталонные JSON-фикстуры тех же моделей + `FactRecord` | при любом изменении сериализации модели — обновить эталон с описанием миграционного пути |
| `tests/test_cli_roundtrip.py` | CLI → файл на диске → CLI читает обратно | новая CLI-команда, изменение пути или формата файла стораджа |
| `tests/test_cli_all_commands.py` | exit code и ключевые строки для каждой публичной CLI-команды | новая CLI-команда — добавить тест успеха + тест ошибки (invalid input / missing entity) |
| `tests/test_domain_invariants.py` | бизнес-правила, которые должны выполняться всегда (newest-first, idempotent reframing, salience bounds, deterministic run_key) | новый инвариант, изменение существующего, новый источник идемпотентности |
| `tests/test_e2e_full_cli.py` | сквозной subprocess-тест §3 A–G одним прогоном | изменение порядка/состава шагов lifecycle |

**Прежде чем закоммитить изменение в порт, модель или CLI**, агент должен
прогнать `uv run pytest tests/test_state_store_contract.py
tests/test_serialization_roundtrip.py tests/test_cli_roundtrip.py
tests/test_domain_invariants.py tests/test_golden_schema.py
tests/test_cli_all_commands.py tests/test_e2e_full_cli.py` локально и
убедиться, что либо все тесты проходят, либо они обновлены под новый
контракт с явным указанием в описании PR.

## 27. Принцип безопасности смысла

Atman строит доверие не тем, что звучит убедительно, а тем, что сохраняет
происхождение смысла.

Поэтому любое значимое утверждение должно быть прослеживаемым:

```text
fact -> experience -> reflection -> identity/narrative/skill
```

Если цепочку нельзя восстановить, утверждение должно быть помечено как
гипотеза, uncertainty или presentation text, но не как устойчивое знание Atman.
## 28. Документация: когда создавать и что писать

### 28.1 Обязательные артефакты при merge PR

Каждый PR, который добавляет или меняет поведение системы, обязан включать:

| Изменение в коде | Обязательный doc-артефакт |
|------------------|--------------------------|
| Новый work package / компонент | `docs/development/work-packages/NN-name.md` |
| Реализованная фича (публичный CLI / API) | `docs/features/<slug>/README.md` + `README-ru.md` |
| Архитектурное решение (breaking change, новый сервис) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Новый порт, адаптер, сервис | обновление `SYSTEM_MAP.md` (§1 маркеры, §2 проводка) |
| Новая CLI-команда | обновление `docs/architecture/codemap/ENDPOINTS.md` (авто при `make codemap`) |
| Новая env-переменная | обновление `.env.example` + `docs/architecture/codemap/STARTUP_DEPS.md` |

PR без нужного doc-артефакта не готов к merge. Исключение: правки в тестах,
опечатки, рефакторинг без изменения публичного контракта — можно указать
`docs: N/A — internal refactor` в описании PR.

### 28.2 Язык документов

- `docs/architecture/`, `docs/design/`, `docs/ops/` — **EN канонический**, RU следом.
- `docs/features/<slug>/README.md` — **EN канонический**, `README-ru.md` следом.
- `docs/development/work-packages/` — **RU** (агент пишет ТЗ на русском для понимания).
- `docs/research/`, `docs/ideas/` — любой язык, RU-пара опциональна.
- `AGENTS.md` — только **EN** (агенты работают на английском).
- `MANIFEST.md`, `SYSTEM.md` — **EN + RU**, оба файла обязательны.

### 28.3 Что писать в design doc (docs/design/)

Минимальная структура `DESIGN_*.md`:

```markdown
# Design — <Title>

> **Type:** Design document
> **Status:** Draft | Review | Decided
> **Date:** YYYY-MM-DD
> **Location:** docs/design/DESIGN_<name>.md

## 1. Problem
<Что не работает или чего не хватает — конкретно.>

## 2. Decision
<Что делаем. Достаточно конкретно чтобы агент мог реализовать без уточнений.>

## 3. Out of scope
<Что явно НЕ входит в это решение.>

## 4. Open questions
<Что ещё не решено. Если пусто — удалить раздел.>
```

Когда design принят → ADR в `docs/architecture/ADR/`.

### 28.4 Что писать в ADR (docs/architecture/ADR/)

```markdown
# ADR-NNN — <Short title>

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNN
**Date:** YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
## Migration impact
```

ADR обязателен (см. §22) при: новом обязательном сервисе, breaking schema change,
смене lifecycle, смене storage boundary, новом типе памяти.

### 28.5 Авто-обновление документации

Скрипт `make codemap` обновляет автоматически:
- `docs/architecture/SYSTEM_MAP.md` — §1 таблицы (модули, порты, адаптеры)
- `docs/architecture/codemap/*` — STARTUP_DEPS, TEST_ENV, ENDPOINTS, DELTA, UNDOCUMENTED
- `README.md` — roadmap-блок и список готовых компонентов
- `AGENTS.md` и `.cursor/rules` — блок с картой документации

Агент **не должен** редактировать эти блоки вручную — правки будут перезаписаны.
Блоки обёрнуты маркерами `<!-- codemap:auto:start ... -->`.

Запускать перед коммитом: `make codemap`. CI упадёт если маркеры устарели.

