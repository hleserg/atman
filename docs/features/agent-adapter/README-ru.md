# Agent Adapter

**Статус:** поставленная runtime-поверхность (E26+)
**Назначение:** обёртка на базе Pydantic AI, позволяющая LLM-агенту проходить через сервисы сессии, памяти, рефлексии, аффекта и навыков Atman.

[[en](README.md)] — *English version*

---

## Обзор

Agent adapter (`src/atman/adapters/agent/`) — LLM-ориентированный
composition-layer Atman. Он не владеет доменным состоянием сам, а собирает
существующие Core-сервисы и порты в запускаемый агентский цикл:

```text
agent input -> AtmanTurn.pre -> pydantic-ai Agent.run -> AtmanTurn.post
```

Поддерживаются два пути интеграции:

- **Интерактивный REPL:** `src/run_agent.py` создаёт или загружает агента из
  agent registry, собирает `AtmanRunner` и запускает полноценную chat-сессию.
- **Встраиваемый host:** `AtmanTurn` даёт per-turn pre/post pipeline для
  Streamlit, session tester или другого host'а, который сам владеет внешним
  chat-loop.

Полный архитектурный поток описан в `docs/architecture/SYSTEM.md`. Операторские
health-check'и для embedded-запусков см. в
`docs/development/SESSION_TESTER_RUNBOOK.md`.

---

## Карта модулей

| Модуль | Публичная поверхность | Роль |
|--------|-----------------------|------|
| `config.py` | `ModelConfig`, `AgentConfig` | Runtime-лимиты и настройки модели: model string, output/context limits, обрезание narrative, RAG-бюджет, режим memory injection, флаг prompt caching. |
| `deps.py` | `AtmanDeps`, `AtmanDeps.from_config(...)` | Замороженный DI-контейнер для `SessionManager`, `IdentityService`, `MicroReflectionService`, `StateStore`, runtime ID и опциональных портов: skill manager, reflection queue, memory guardian, ambient memory, maintenance worker. |
| `factory.py` | `build_deps(...)`, builders reflection-сервисов | Composition root. Подключает storage, affect, divergence, post-write scheduler, memory guardian, passive/ambient RAG, skills, maintenance и reflection services. |
| `runner.py` | `AtmanRunner`, `AtmanTurn` | Полный REPL-runner и встраиваемый per-turn pipeline. Отвечает за start/finish сессии, restart/wait sentinel'ы, memory injection, post-turn affect/refusal analysis и maintenance drain. |
| `instructions.py` | `build_instructions(...)`, `build_memory_context(...)`, `build_skill_suggestions_section(...)` | Разделяет стабильные behavioral rules и личную память. Память входит через `inject_memory()`, кроме режима `memory_injection_mode="system_prompt"`. |
| `memory_injection.py` | `inject_memory(...)`, `MemoryInjectionMode` | Доставляет recalled context как assistant message, user message или расширение system prompt. |
| `tools.py` | `record_key_moment`, `log_experience`, `restart_session`, `wait_session`, `resolve_pending_review`, `request_reflection` | Tool-callback'и Pydantic AI и sentinel'ы runner'а. |
| `preflight.py` | `run_cli_preflight(...)`, `run_streamlit_preflight(...)` | Проверки готовности локальной модели, PostgreSQL и NLP-зависимостей. |

Важно про импорты: `atman.adapters.agent.__all__` экспортирует config,
dependency, instruction, token monitor и базовые tool-символы. `AtmanRunner`,
`AtmanTurn` и `build_deps` импортируйте из их submodule'ей.

---

## Быстрый старт: REPL

`src/run_agent.py` использует `AgentsRegistry`, поэтому REPL-путь требует
`DATABASE_URL` (или `.env` с `DATABASE_URL`), хотя нижележащий `build_deps(...)`
может падать обратно на file storage для dev/test-сборки без БД.

```bash
# Список зарегистрированных агентов.
uv run src/run_agent.py --list

# Создать зарегистрированного агента и workspace в ~/.atman/agents/<serial_id>/.
uv run src/run_agent.py --new "research assistant"

# Продолжить агента #1 с явным Pydantic AI model string.
uv run src/run_agent.py --agent 1 --model ollama:qwen3.5:9b
```

Корневой workspace по умолчанию — `~/.atman/agents`. Для тестов на временном
состоянии используйте `--workspace-root`.

---

## Встраиваемый путь: `AtmanTurn`

Используйте `AtmanTurn`, когда внешнее приложение владеет chat-loop, но должно
оборачивать каждый model turn lifecycle'ом Atman:

```python
turn = AtmanTurn(deps, session_manager, session_id)
deps_for_run = turn.pre(user_text)
result = await agent.run(user_text, deps=deps_for_run, message_history=history)
turn.post(result.output)
```

`AtmanTurn.pre(...)` выполняет регистрацию entities, passive RAG, ambient RAG и
инъекцию skill suggestions. `AtmanTurn.post(...)` записывает ответ ассистента,
запускает affect/refusal hooks, может автоматически записывать key moments для
boundary markers и сливает maintenance work, если worker подключён.

---

## Инструменты агента

| Tool | Поведение backend'а | Доступность |
|------|---------------------|-------------|
| `record_key_moment` | Валидирует emotional values и отправляет `AgentMemoryReport` в `AffectDetector.submit_self_report(...)`. Возвращает строки ошибок вместо raise, чтобы LLM мог исправить вызов. | Требует активную сессию и affect detector на `SessionManager`. |
| `log_experience` | Deprecated redirect. Сообщает агенту использовать `record_key_moment`; session-level `Experience` сохраняется при завершении сессии. | Всегда безопасен как migration shim. |
| `restart_session` | Возвращает sentinel `__ATMAN_RESTART_REQUESTED__`. Реальным restart lifecycle владеет `AtmanRunner`. | REPL runner path. |
| `wait_session` | Возвращает sentinel `__ATMAN_WAIT_REQUESTED__<minutes>`. Реальным wait-loop владеет `AtmanRunner`. | REPL runner path. |
| `resolve_pending_review` | Закрывает item в `PendingHumanReviewInbox`. | Регистрируется только при наличии `AtmanDeps.pending_review_inbox`. |
| `request_reflection` | Добавляет `ReflectionRequest` с идемпотентным hourly run key. | Регистрируется только при наличии `AtmanDeps.reflection_request_queue`. |

Ограничение: `record_key_moment` больше не пишет через
`SessionManager.record_key_moment`; legacy-метод намеренно падает. Поддерживаемый
путь — affect self-reporting, см. `docs/features/affect-detector/README.md`.

---

## Конфигурация

| Настройка | Где | Эффект |
|-----------|-----|--------|
| `DATABASE_URL` / `ATMAN_DB_URL` | environment | Включает Postgres-backed state, когда агент есть в `public.agents`; иначе `factory.py` падает обратно на file storage. `src/run_agent.py` требует `DATABASE_URL` для `AgentsRegistry`. |
| `ATMAN_LINGUISTIC_ENABLED=true` | environment | Включает реальный linguistic/RAG path при установленных optional dependencies. Иначе factory использует no-op analyzers и сохраняет session path рабочим. |
| `ATMAN_SKILLS_ENABLED` | environment | Переопределяет settings-level включение skill-loop. Falsy-значения (`false`, `0`, `no`, `off`) отключают skill wiring. |
| `ATMAN_LLM_BASE_URL`, `ATMAN_LLM_MODEL`, `ATMAN_LLM_API_KEY` | environment | Включают реальную OpenAI-compatible reflection model для narrative/reflection wiring; иначе mock reflection models оставляют dev/test-запуски локальными. |
| `ATMAN_SESSION_LOG`, `ATMAN_SESSION_LOG_FILE` | environment | Управляют JSONL session debug log. Включён по умолчанию, если не задано `0`, `false`, `no` или `off`. |
| `ATMAN_OBS_LEVEL` | environment | Управляет observability level (`off`, `minimal`, `debug`, `verbose`). См. `docs/features/observability/levels.md`. |
| `AgentConfig.memory_injection_mode` | code/config | Выбирает доставку памяти: `assistant_message` (default), `user_message` или `system_prompt`. |
| `AgentConfig.rag_token_budget` | code/config | Ограничивает per-request RAG context по принятой в репозитории token heuristic. |
| `AgentConfig.max_tool_calls` | code/config | Валидируется и переносится в `AtmanDeps`; enforcement dispatch'а ещё не реализован. |

---

## Известные ограничения

- Таргета `make demo-agent` пока нет. Используйте `uv run src/run_agent.py ...`.
- `enable_experience_search` есть в `AgentConfig`, но прямой experience search
  tool сейчас не экспортируется.
- `max_tool_calls` валидируется, но runner dispatch loop пока его не enforce'ит.
- Postgres-backed REPL-запуски требуют agent registry. Нижележащие factory-тесты
  могут использовать file/in-memory fallbacks без внешних сервисов.
- Опциональные NLP, skill, reflection и observability подсистемы деградируют до
  no-op или in-memory реализаций, когда зависимости или env flags отсутствуют.

---

## Тесты

Фокусные проверки adapter'а:

```bash
pytest tests/test_agent_config.py tests/test_instructions.py tests/test_tools.py \
       tests/test_runner.py tests/test_atman_turn.py tests/test_skill_factory_wiring.py -v
```

Для docs-only правок минимум:

```bash
git diff --check
```

Для изменений кода в этой зоне запускайте полный quality gate:

```bash
make check
```
